use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::{Duration, UNIX_EPOCH};

use anyhow::Result;
use once_cell::sync::Lazy;
use regex::Regex;
use tantivy::collector::TopDocs;
use tantivy::query::{AllQuery, QueryParser};
use tantivy::schema::*;
use tantivy::{
    doc, DateTime, Index, IndexReader, IndexWriter, ReloadPolicy, SnippetGenerator, TantivyDocument,
};
use tantivy::schema::OwnedValue;
use tantivy::directory::MmapDirectory;

use crate::error::AppError;
use crate::models::SearchResult;

const SCHEMA_VERSION: &str = "1";
const SCHEMA_VERSION_FILE: &str = ".schema_version";
const MAX_RETRIES: u32 = 8;
const RETRY_DELAY: Duration = Duration::from_millis(250);

static TAG_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(^|\s)#([a-zA-Z0-9_-]+)").unwrap()
});

static CODEBLOCK_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"`{1,3}[^`]*`{1,3}").unwrap()
});

#[derive(Clone)]
pub struct SearchIndex {
    index: Index,
    reader: IndexReader,
    schema: NoteSchema,
    notes_path: PathBuf,
}

#[derive(Clone)]
struct NoteSchema {
    schema: Schema,
    filename: Field,
    last_modified: Field,
    title: Field,
    content: Field,
    tags: Field,
}

impl SearchIndex {
    pub fn open(notes_path: impl Into<PathBuf>, index_path: impl Into<PathBuf>) -> Result<Self> {
        let notes_path = notes_path.into();
        let index_path = index_path.into();

        let note_schema = build_schema();
        let index = load_or_create_index(&index_path, &note_schema)?;

        let reader = index
            .reader_builder()
            .reload_policy(ReloadPolicy::OnCommitWithDelay)
            .try_into()?;

        let slf = Self {
            index,
            reader,
            schema: note_schema,
            notes_path,
        };

        // Initial sync
        slf.sync_with_retry(false)?;

        Ok(slf)
    }

    // ── Public API ──────────────────────────────────────────────────────────

    pub fn search(
        &self,
        term: &str,
        sort: &str,
        order: &str,
        limit: Option<usize>,
    ) -> Result<Vec<SearchResult>, AppError> {
        self.sync_with_retry(false).map_err(AppError::Internal)?;

        let searcher = self.reader.searcher();
        let limit = limit.unwrap_or(1000).max(1);
        let preprocessed = preprocess_term(term);

        if preprocessed == "*" {
            self.search_all(&searcher, sort, order, limit)
        } else {
            self.search_term(&searcher, &preprocessed, sort, order, limit)
        }
    }

    pub fn get_tags(&self) -> Result<Vec<String>, AppError> {
        self.sync_with_retry(false).map_err(AppError::Internal)?;
        let searcher = self.reader.searcher();
        let mut tags = HashSet::new();
        for seg_reader in searcher.segment_readers() {
            let inv = seg_reader
                .inverted_index(self.schema.tags)
                .map_err(|e| AppError::Internal(e.into()))?;
            let mut terms_iter = inv
                .terms()
                .stream()
                .map_err(|e| AppError::Internal(e.into()))?;
            while terms_iter.advance() {
                let key = terms_iter.key();
                if let Ok(s) = std::str::from_utf8(key) {
                    if !s.is_empty() {
                        tags.insert(s.to_string());
                    }
                }
            }
        }
        let mut sorted: Vec<String> = tags.into_iter().collect();
        sorted.sort();
        Ok(sorted)
    }

    // ── Index sync ──────────────────────────────────────────────────────────

    fn sync_with_retry(&self, optimize: bool) -> Result<()> {
        let mut last_err: Option<anyhow::Error> = None;
        for attempt in 0..MAX_RETRIES {
            match self.index.writer(50_000_000) {
                Ok(writer) => return self.do_sync(writer, optimize),
                Err(e) => {
                    if attempt > 0 {
                        tracing::warn!("Index lock retry {attempt}/{MAX_RETRIES}: {e}");
                    }
                    std::thread::sleep(RETRY_DELAY);
                    last_err = Some(e.into());
                }
            }
        }
        Err(last_err.unwrap())
    }

    fn do_sync(&self, mut writer: IndexWriter, optimize: bool) -> Result<()> {
        let searcher = self.reader.searcher();

        // Collect currently indexed filenames → last_modified
        let mut indexed: HashMap<String, i64> = HashMap::new();
        for seg in searcher.segment_readers() {
            let store = seg.get_store_reader(0)?;
            for doc_addr in 0..seg.num_docs() {
                if let Ok(doc) = store.get::<TantivyDocument>(doc_addr) {
                    let fname = doc
                        .get_first(self.schema.filename)
                        .and_then(|v| if let OwnedValue::Str(s) = v { Some(s.clone()) } else { None });
                    let lm = doc
                        .get_first(self.schema.last_modified)
                        .and_then(|v| if let OwnedValue::Date(d) = v { Some(d.into_timestamp_secs()) } else { None });
                    if let (Some(f), Some(l)) = (fname, lm) {
                        indexed.insert(f, l);
                    }
                }
            }
        }

        // Scan filesystem
        let mut on_disk: HashSet<String> = HashSet::new();
        if let Ok(entries) = std::fs::read_dir(&self.notes_path) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().and_then(|e| e.to_str()) == Some("md") {
                    if let Some(fname) = p.file_name().and_then(|n| n.to_str()) {
                        let fname = fname.to_string();
                        on_disk.insert(fname.clone());

                        let disk_mtime = file_mtime_secs(&p).unwrap_or(0);
                        let indexed_mtime = indexed.get(&fname).copied().unwrap_or(-1);

                        if disk_mtime != indexed_mtime {
                            let title = fname.trim_end_matches(".md");
                            let content = std::fs::read_to_string(&p).unwrap_or_default();
                            let (content_no_tags, tags) = extract_tags(&content);
                            let dt = DateTime::from_timestamp_secs(disk_mtime);

                            writer.delete_term(Term::from_field_text(
                                self.schema.filename,
                                &fname,
                            ));
                            writer.add_document(doc!(
                                self.schema.filename => fname.as_str(),
                                self.schema.last_modified => dt,
                                self.schema.title => title,
                                self.schema.content => content_no_tags.as_str(),
                                self.schema.tags => tags.join(" ").as_str(),
                            ))?;
                            tracing::info!("Indexed: {fname}");
                        }
                    }
                }
            }
        }

        // Delete removed notes
        for fname in indexed.keys() {
            if !on_disk.contains(fname.as_str()) {
                writer.delete_term(Term::from_field_text(self.schema.filename, fname));
                tracing::info!("Removed from index: {fname}");
            }
        }

        writer.commit()?;

        if optimize {
            let mut w2: IndexWriter<TantivyDocument> = self.index.writer(50_000_000)?;
            let seg_ids = self.index.searchable_segment_ids()?;
            if seg_ids.len() > 1 {
                let merge = w2.merge(&seg_ids);
                let _ = merge.wait();
            }
        }

        Ok(())
    }

    // ── Search helpers ──────────────────────────────────────────────────────

    fn search_all(
        &self,
        searcher: &tantivy::Searcher,
        sort: &str,
        order: &str,
        limit: usize,
    ) -> Result<Vec<SearchResult>, AppError> {
        let top_docs = searcher
            .search(&AllQuery, &TopDocs::with_limit(limit))
            .map_err(|e| AppError::Internal(e.into()))?;

        let mut results: Vec<SearchResult> = top_docs
            .into_iter()
            .map(|(_, addr)| {
                let doc: TantivyDocument = searcher.doc(addr).unwrap();
                self.doc_to_search_result(&doc, None, None, None)
            })
            .collect();

        sort_results(&mut results, sort, order);
        Ok(results)
    }

    fn search_term(
        &self,
        searcher: &tantivy::Searcher,
        term: &str,
        sort: &str,
        order: &str,
        limit: usize,
    ) -> Result<Vec<SearchResult>, AppError> {
        let fields = if term.contains('"') {
            vec![self.schema.title, self.schema.content]
        } else {
            vec![self.schema.title, self.schema.content, self.schema.tags]
        };

        let mut parser = QueryParser::for_index(&self.index, fields);
        parser.set_field_boost(self.schema.title, 2.0);
        parser.set_field_boost(self.schema.tags, 2.0);

        let query = parser
            .parse_query(term)
            .map_err(|e| AppError::BadRequest(e.to_string()))?;

        let top_docs = searcher
            .search(&*query, &TopDocs::with_limit(limit))
            .map_err(|e| AppError::Internal(e.into()))?;

        let title_snippet_gen =
            SnippetGenerator::create(searcher, &*query, self.schema.title)
                .map_err(|e| AppError::Internal(e.into()))?;
        let mut content_snippet_gen =
            SnippetGenerator::create(searcher, &*query, self.schema.content)
                .map_err(|e| AppError::Internal(e.into()))?;
        content_snippet_gen.set_max_num_chars(200);

        let mut results: Vec<SearchResult> = top_docs
            .into_iter()
            .map(|(score, addr)| {
                let doc: TantivyDocument = searcher.doc(addr).unwrap();
                let title_snip = title_snippet_gen.snippet_from_doc(&doc);
                let content_snip = content_snippet_gen.snippet_from_doc(&doc);
                let tag_matches = extract_tag_matches(&doc, self.schema.tags, term);
                let mut sr = self.doc_to_search_result(
                    &doc,
                    Some(render_snippet(&title_snip)),
                    Some(render_snippet(&content_snip)).filter(|s| !s.is_empty()),
                    tag_matches,
                );
                sr.score = Some(score);
                sr
            })
            .collect();

        sort_results(&mut results, sort, order);
        Ok(results)
    }

    fn doc_to_search_result(
        &self,
        doc: &TantivyDocument,
        title_highlights: Option<String>,
        content_highlights: Option<String>,
        tag_matches: Option<Vec<String>>,
    ) -> SearchResult {
        let title = doc
            .get_first(self.schema.filename)
            .and_then(|v| if let OwnedValue::Str(s) = v { Some(s.trim_end_matches(".md").to_string()) } else { None })
            .unwrap_or_default();

        let last_modified = doc
            .get_first(self.schema.last_modified)
            .and_then(|v| if let OwnedValue::Date(d) = v { Some(d.into_timestamp_secs() as f64) } else { None })
            .unwrap_or(0.0);

        SearchResult {
            title,
            last_modified,
            score: None,
            title_highlights,
            content_highlights,
            tag_matches,
        }
    }
}

// ── Schema ──────────────────────────────────────────────────────────────────

fn build_schema() -> NoteSchema {
    let mut b = Schema::builder();

    let filename = b.add_text_field("filename", STRING | STORED | FAST);
    let last_modified = b.add_date_field(
        "last_modified",
        DateOptions::default()
            .set_stored()
            .set_fast()
            .set_indexed(),
    );
    let title = b.add_text_field(
        "title",
        TextOptions::default()
            .set_indexing_options(
                TextFieldIndexing::default()
                    .set_tokenizer("stemming_folding")
                    .set_index_option(IndexRecordOption::WithFreqsAndPositions),
            )
            .set_stored(),
    );
    let content = b.add_text_field(
        "content",
        TextOptions::default().set_indexing_options(
            TextFieldIndexing::default()
                .set_tokenizer("stemming_folding")
                .set_index_option(IndexRecordOption::WithFreqsAndPositions),
        ),
    );
    let tags = b.add_text_field(
        "tags",
        TextOptions::default().set_indexing_options(
            TextFieldIndexing::default()
                .set_tokenizer("whitespace_lower")
                .set_index_option(IndexRecordOption::WithFreqs),
        ),
    );

    NoteSchema { schema: b.build(), filename, last_modified, title, content, tags }
}

fn register_tokenizers(index: &Index) {
    use tantivy::tokenizer::{
        AsciiFoldingFilter, Language, LowerCaser, RemoveLongFilter, SimpleTokenizer, Stemmer,
        TextAnalyzer, WhitespaceTokenizer,
    };

    let stemming_folding = TextAnalyzer::builder(SimpleTokenizer::default())
        .filter(RemoveLongFilter::limit(40))
        .filter(LowerCaser)
        .filter(AsciiFoldingFilter)
        .filter(Stemmer::new(Language::English))
        .build();
    index.tokenizers().register("stemming_folding", stemming_folding);

    let whitespace_lower = TextAnalyzer::builder(WhitespaceTokenizer::default())
        .filter(LowerCaser)
        .build();
    index.tokenizers().register("whitespace_lower", whitespace_lower);
}

fn load_or_create_index(index_path: &Path, note_schema: &NoteSchema) -> Result<Index> {
    std::fs::create_dir_all(index_path)?;

    let version_file = index_path.join(SCHEMA_VERSION_FILE);
    let existing_version = std::fs::read_to_string(&version_file).unwrap_or_default();

    let dir = MmapDirectory::open(index_path)?;
    let index_exists = Index::exists(&dir)?;

    if existing_version.trim() != SCHEMA_VERSION && index_exists {
        tracing::info!("Index schema version mismatch — rebuilding");
        let _ = std::fs::remove_dir_all(index_path);
        std::fs::create_dir_all(index_path)?;
    }

    let index = if index_exists && existing_version.trim() == SCHEMA_VERSION {
        tracing::info!("Opening existing index at {}", index_path.display());
        Index::open_in_dir(index_path)?
    } else {
        tracing::info!("Creating index at {}", index_path.display());
        Index::create_in_dir(index_path, note_schema.schema.clone())?
    };

    register_tokenizers(&index);
    std::fs::write(version_file, SCHEMA_VERSION)?;
    Ok(index)
}

// ── Tag extraction ──────────────────────────────────────────────────────────

fn extract_tags(content: &str) -> (String, Vec<String>) {
    let stripped = CODEBLOCK_RE.replace_all(content, "");
    let mut tags = HashSet::new();
    for cap in TAG_RE.captures_iter(&stripped) {
        tags.insert(cap[2].to_lowercase());
    }
    let content_no_tags = TAG_RE
        .replace_all(content, |caps: &regex::Captures| caps[1].to_string())
        .to_string();
    let mut sorted: Vec<String> = tags.into_iter().collect();
    sorted.sort();
    (content_no_tags, sorted)
}

fn extract_tag_matches(doc: &TantivyDocument, tags_field: Field, term: &str) -> Option<Vec<String>> {
    let tags_val = doc
        .get_first(tags_field)
        .and_then(|v| if let OwnedValue::Str(s) = v { Some(s.clone()) } else { None })
        .unwrap_or_default();
    if tags_val.is_empty() {
        return None;
    }
    let indexed: HashSet<&str> = tags_val.split_whitespace().collect();
    let matched: Vec<String> = indexed
        .iter()
        .filter(|&&t| term.contains(&format!("tags:{t}")) || term.contains(&format!("#{t}")))
        .map(|s| s.to_string())
        .collect();
    if matched.is_empty() { None } else { Some(matched) }
}

// ── Preprocessing ─────────────────────────────────────────────────────────────

fn preprocess_term(term: &str) -> String {
    let t = term.trim();
    TAG_RE
        .replace_all(t, |caps: &regex::Captures| {
            format!("{}tags:{}", &caps[1], &caps[2])
        })
        .into_owned()
}

// ── Sorting ───────────────────────────────────────────────────────────────────

fn sort_results(results: &mut Vec<SearchResult>, sort: &str, order: &str) {
    let ascending = order == "asc";
    match sort {
        "title" => results.sort_by(|a, b| {
            let cmp = a.title.to_lowercase().cmp(&b.title.to_lowercase());
            if ascending { cmp } else { cmp.reverse() }
        }),
        "lastModified" => results.sort_by(|a, b| {
            let cmp = a.last_modified.partial_cmp(&b.last_modified).unwrap_or(std::cmp::Ordering::Equal);
            if ascending { cmp } else { cmp.reverse() }
        }),
        _ => {
            // score: tantivy already returns in score-desc order
            // flip if ascending requested
            if ascending {
                results.sort_by(|a, b| {
                    a.score.unwrap_or(0.0)
                        .partial_cmp(&b.score.unwrap_or(0.0))
                        .unwrap_or(std::cmp::Ordering::Equal)
                });
            }
        }
    }
}

// ── Snippet rendering ─────────────────────────────────────────────────────────

fn render_snippet(snippet: &tantivy::Snippet) -> String {
    let text = snippet.fragment();
    let mut html = String::new();
    let mut last = 0usize;
    for range in snippet.highlighted() {
        html.push_str(&html_escape(&text[last..range.start]));
        html.push_str(r#"<strong class="match">"#);
        html.push_str(&html_escape(&text[range.start..range.end]));
        html.push_str("</strong>");
        last = range.end;
    }
    html.push_str(&html_escape(&text[last..]));
    html
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn file_mtime_secs(path: &Path) -> Option<i64> {
    std::fs::metadata(path)
        .ok()?
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|d| d.as_secs() as i64)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_index(dir: &tempfile::TempDir) -> SearchIndex {
        let notes = dir.path().to_path_buf();
        let idx = dir.path().join(".index");
        SearchIndex::open(notes, idx).unwrap()
    }

    fn write_note(dir: &tempfile::TempDir, title: &str, content: &str) {
        std::fs::write(dir.path().join(format!("{title}.md")), content).unwrap();
    }

    // ── Tag extraction ─────────────────────────────────────────────────────────

    #[test]
    fn test_extract_tags_basic() {
        let (_, tags) = extract_tags("hello #world and #foo");
        assert!(tags.contains(&"world".to_string()));
        assert!(tags.contains(&"foo".to_string()));
    }

    #[test]
    fn test_extract_tags_lowercases() {
        let (_, tags) = extract_tags("#Python is #GREAT");
        assert!(tags.contains(&"python".to_string()));
        assert!(tags.contains(&"great".to_string()));
    }

    #[test]
    fn test_extract_tags_ignores_codeblock() {
        let (_, tags) = extract_tags("text `#notag` and #realtag");
        assert!(!tags.contains(&"notag".to_string()));
        assert!(tags.contains(&"realtag".to_string()));
    }

    #[test]
    fn test_extract_tags_removes_from_content() {
        let (content, _) = extract_tags("some text #tag more text");
        assert!(!content.contains("#tag"));
    }

    // ── Preprocessing ──────────────────────────────────────────────────────────

    #[test]
    fn test_preprocess_replaces_hashtag() {
        let result = preprocess_term("#python");
        assert!(result.contains("tags:python"), "got: {result}");
    }

    #[test]
    fn test_preprocess_no_hashtag() {
        assert_eq!(preprocess_term("python"), "python");
    }

    #[test]
    fn test_preprocess_strips_whitespace() {
        assert_eq!(preprocess_term("  hello  "), "hello");
    }

    #[test]
    fn test_preprocess_mixed() {
        let result = preprocess_term("notes #python");
        assert!(result.contains("tags:python"), "got: {result}");
        assert!(result.contains("notes"));
    }

    // ── Search ─────────────────────────────────────────────────────────────────

    #[test]
    fn test_search_finds_note() {
        let dir = tempfile::tempdir().unwrap();
        write_note(&dir, "rust", "Rust is a systems language");
        let idx = make_index(&dir);
        let results = idx.search("systems", "score", "desc", None).unwrap();
        assert!(results.iter().any(|r| r.title == "rust"));
    }

    #[test]
    fn test_search_wildcard_returns_all() {
        let dir = tempfile::tempdir().unwrap();
        write_note(&dir, "note1", "first note");
        write_note(&dir, "note2", "second note");
        let idx = make_index(&dir);
        let results = idx.search("*", "score", "desc", None).unwrap();
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn test_search_no_results() {
        let dir = tempfile::tempdir().unwrap();
        write_note(&dir, "note1", "hello world");
        let idx = make_index(&dir);
        let results = idx.search("xyzzy_nonexistent", "score", "desc", None).unwrap();
        assert!(results.is_empty());
    }

    #[test]
    fn test_search_limit() {
        let dir = tempfile::tempdir().unwrap();
        for i in 0..5 {
            write_note(&dir, &format!("note{i}"), "common keyword");
        }
        let idx = make_index(&dir);
        let results = idx.search("common", "score", "desc", Some(3)).unwrap();
        assert_eq!(results.len(), 3);
    }

    #[test]
    fn test_search_by_tag() {
        let dir = tempfile::tempdir().unwrap();
        write_note(&dir, "tagged", "some content #mytag");
        write_note(&dir, "untagged", "other content");
        let idx = make_index(&dir);
        let results = idx.search("#mytag", "score", "desc", None).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].title, "tagged");
    }

    #[test]
    fn test_get_tags() {
        let dir = tempfile::tempdir().unwrap();
        write_note(&dir, "a", "content #alpha");
        write_note(&dir, "b", "content #beta");
        let idx = make_index(&dir);
        let tags = idx.get_tags().unwrap();
        assert!(tags.contains(&"alpha".to_string()));
        assert!(tags.contains(&"beta".to_string()));
    }

    // ── Version ────────────────────────────────────────────────────────────────

    #[test]
    fn test_version_is_semver() {
        let version = env!("CARGO_PKG_VERSION");
        let re = regex::Regex::new(r"^\d+\.\d+\.\d+(-[a-z]+\.\d+)?$").unwrap();
        assert!(re.is_match(version), "version '{version}' is not semver");
    }
}
