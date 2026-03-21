use serde::{Deserialize, Serialize};

// ── Notes ──────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Note {
    pub title: String,
    pub content: Option<String>,
    pub last_modified: f64,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NoteCreate {
    pub title: String,
    pub content: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NoteUpdate {
    pub new_title: Option<String>,
    pub new_content: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchResult {
    pub title: String,
    pub last_modified: f64,
    pub score: Option<f32>,
    pub title_highlights: Option<String>,
    pub content_highlights: Option<String>,
    pub tag_matches: Option<Vec<String>>,
}

// ── Auth ────────────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub token_type: String,
}

// ── Attachments ─────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AttachmentCreateResponse {
    pub filename: String,
    pub url: String,
}

// ── Config ───────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConfigResponse {
    pub auth_type: String,
    pub quick_access_hide: bool,
    pub quick_access_title: String,
    pub quick_access_term: String,
    pub quick_access_sort: String,
    pub quick_access_limit: u32,
}
