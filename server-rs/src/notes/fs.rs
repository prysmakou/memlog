use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use crate::error::{validate_filename, AppError};
use crate::models::{Note, NoteCreate, NoteUpdate};

pub struct NoteStore {
    path: PathBuf,
}

impl NoteStore {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    pub fn notes_path(&self) -> &Path {
        &self.path
    }

    fn note_path(&self, title: &str) -> PathBuf {
        self.path.join(format!("{title}.md"))
    }

    pub async fn get(&self, title: &str) -> Result<Note, AppError> {
        validate_filename(title)?;
        let p = self.note_path(title);
        let content = tokio::fs::read_to_string(&p)
            .await
            .map_err(|_| AppError::NoteNotFound)?;
        let last_modified = mtime(&p)?;
        Ok(Note { title: title.to_string(), content: Some(content), last_modified })
    }

    pub async fn create(&self, data: NoteCreate) -> Result<Note, AppError> {
        let title = data.title.trim().to_string();
        validate_filename(&title)?;
        let p = self.note_path(&title);
        if p.exists() {
            return Err(AppError::NoteExists);
        }
        let content = data.content.unwrap_or_default();
        tokio::fs::write(&p, &content)
            .await
            .map_err(|e| AppError::Internal(e.into()))?;
        let last_modified = mtime(&p)?;
        Ok(Note { title, content: Some(content), last_modified })
    }

    pub async fn update(&self, title: &str, data: NoteUpdate) -> Result<Note, AppError> {
        validate_filename(title)?;
        let mut p = self.note_path(title);
        if !p.exists() {
            return Err(AppError::NoteNotFound);
        }

        // Rename if requested
        let final_title = if let Some(ref new_title) = data.new_title {
            let new_title = new_title.trim().to_string();
            validate_filename(&new_title)?;
            let new_p = self.note_path(&new_title);
            if new_p.exists() && new_p != p {
                return Err(AppError::NoteExists);
            }
            tokio::fs::rename(&p, &new_p)
                .await
                .map_err(|e| AppError::Internal(e.into()))?;
            p = new_p;
            new_title
        } else {
            title.to_string()
        };

        // Update content if requested
        if let Some(ref content) = data.new_content {
            tokio::fs::write(&p, content)
                .await
                .map_err(|e| AppError::Internal(e.into()))?;
        }

        let content = tokio::fs::read_to_string(&p)
            .await
            .map_err(|_| AppError::NoteNotFound)?;
        let last_modified = mtime(&p)?;
        Ok(Note { title: final_title, content: Some(content), last_modified })
    }

    pub async fn delete(&self, title: &str) -> Result<(), AppError> {
        validate_filename(title)?;
        let p = self.note_path(title);
        tokio::fs::remove_file(&p)
            .await
            .map_err(|_| AppError::NoteNotFound)
    }
}

pub fn mtime(path: &Path) -> Result<f64, AppError> {
    let meta = std::fs::metadata(path).map_err(|_| AppError::NoteNotFound)?;
    let secs = meta
        .modified()
        .map_err(|e| AppError::Internal(e.into()))?
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    Ok(secs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{NoteCreate, NoteUpdate};

    fn store(dir: &tempfile::TempDir) -> NoteStore {
        NoteStore::new(dir.path())
    }

    // ── Create ────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_create_and_get() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "hello".into(), content: Some("world".into()) })
            .await
            .unwrap();
        let note = s.get("hello").await.unwrap();
        assert_eq!(note.title, "hello");
        assert_eq!(note.content.as_deref(), Some("world"));
    }

    #[tokio::test]
    async fn test_create_returns_last_modified() {
        let dir = tempfile::tempdir().unwrap();
        let note = store(&dir)
            .create(NoteCreate { title: "t".into(), content: Some("c".into()) })
            .await
            .unwrap();
        assert!(note.last_modified > 0.0);
    }

    #[tokio::test]
    async fn test_create_duplicate_fails() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "dup".into(), content: None }).await.unwrap();
        let err = s.create(NoteCreate { title: "dup".into(), content: None }).await.unwrap_err();
        assert!(matches!(err, AppError::NoteExists));
    }

    #[tokio::test]
    async fn test_create_invalid_title_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir)
            .create(NoteCreate { title: "bad<title".into(), content: None })
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::InvalidTitle(_)));
    }

    #[tokio::test]
    async fn test_create_strips_whitespace_from_title() {
        let dir = tempfile::tempdir().unwrap();
        let note = store(&dir)
            .create(NoteCreate { title: "  trimmed  ".into(), content: None })
            .await
            .unwrap();
        assert_eq!(note.title, "trimmed");
    }

    // ── Get ───────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_get_missing_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir).get("nope").await.unwrap_err();
        assert!(matches!(err, AppError::NoteNotFound));
    }

    #[tokio::test]
    async fn test_get_invalid_title_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir).get("bad<title").await.unwrap_err();
        assert!(matches!(err, AppError::InvalidTitle(_)));
    }

    // ── Update ────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_update_content() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "n".into(), content: Some("old".into()) }).await.unwrap();
        let note = s
            .update("n", NoteUpdate { new_title: None, new_content: Some("new".into()) })
            .await
            .unwrap();
        assert_eq!(note.content.as_deref(), Some("new"));
    }

    #[tokio::test]
    async fn test_update_title() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "old".into(), content: Some("content".into()) })
            .await
            .unwrap();
        let note = s
            .update("old", NoteUpdate { new_title: Some("new".into()), new_content: None })
            .await
            .unwrap();
        assert_eq!(note.title, "new");
        assert_eq!(note.content.as_deref(), Some("content"));
        assert!(s.get("old").await.is_err());
    }

    #[tokio::test]
    async fn test_update_title_and_content() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "orig".into(), content: Some("orig content".into()) })
            .await
            .unwrap();
        let note = s
            .update(
                "orig",
                NoteUpdate {
                    new_title: Some("renamed".into()),
                    new_content: Some("new content".into()),
                },
            )
            .await
            .unwrap();
        assert_eq!(note.title, "renamed");
        assert_eq!(note.content.as_deref(), Some("new content"));
    }

    #[tokio::test]
    async fn test_update_title_conflict_fails() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "a".into(), content: None }).await.unwrap();
        s.create(NoteCreate { title: "b".into(), content: None }).await.unwrap();
        let err = s
            .update("a", NoteUpdate { new_title: Some("b".into()), new_content: None })
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::NoteExists));
    }

    #[tokio::test]
    async fn test_update_missing_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir)
            .update("ghost", NoteUpdate { new_title: None, new_content: Some("x".into()) })
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::NoteNotFound));
    }

    #[tokio::test]
    async fn test_update_invalid_title_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir)
            .update("bad<title", NoteUpdate { new_title: None, new_content: None })
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::InvalidTitle(_)));
    }

    // ── Delete ────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_delete_note() {
        let dir = tempfile::tempdir().unwrap();
        let s = store(&dir);
        s.create(NoteCreate { title: "bye".into(), content: None }).await.unwrap();
        s.delete("bye").await.unwrap();
        assert!(s.get("bye").await.is_err());
    }

    #[tokio::test]
    async fn test_delete_missing_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir).delete("ghost").await.unwrap_err();
        assert!(matches!(err, AppError::NoteNotFound));
    }

    #[tokio::test]
    async fn test_delete_invalid_title_fails() {
        let dir = tempfile::tempdir().unwrap();
        let err = store(&dir).delete("bad<title").await.unwrap_err();
        assert!(matches!(err, AppError::InvalidTitle(_)));
    }
}
