use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("Note not found")]
    NoteNotFound,
    #[error("Note already exists")]
    NoteExists,
    #[error("Attachment not found")]
    AttachmentNotFound,
    #[error("Invalid title: {0}")]
    InvalidTitle(String),
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Bad request: {0}")]
    BadRequest(String),
    #[error("Internal error: {0}")]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, msg) = match &self {
            AppError::NoteNotFound => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::NoteExists => (StatusCode::CONFLICT, self.to_string()),
            AppError::AttachmentNotFound => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::InvalidTitle(m) => (StatusCode::BAD_REQUEST, m.clone()),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::BadRequest(m) => (StatusCode::BAD_REQUEST, m.clone()),
            AppError::Internal(e) => {
                tracing::error!("Internal error: {e:#}");
                (StatusCode::INTERNAL_SERVER_ERROR, "Internal server error".to_string())
            }
        };
        (status, Json(json!({"detail": msg}))).into_response()
    }
}

pub fn validate_filename(name: &str) -> Result<(), AppError> {
    let forbidden: &[char] = &['<', '>', ':', '"', '/', '\\', '|', '?', '*'];
    if let Some(c) = name.chars().find(|c| forbidden.contains(c)) {
        return Err(AppError::InvalidTitle(format!(
            "Title contains forbidden character: '{c}'"
        )));
    }
    if name.trim().is_empty() {
        return Err(AppError::InvalidTitle("Title cannot be empty".to_string()));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_filename() {
        assert!(validate_filename("my-note").is_ok());
        assert!(validate_filename("hello world").is_ok());
        assert!(validate_filename("note_2024").is_ok());
    }

    #[test]
    fn test_invalid_filename_forbidden_chars() {
        for c in &['<', '>', ':', '"', '/', '\\', '|', '?', '*'] {
            let title = format!("bad{c}title");
            assert!(
                validate_filename(&title).is_err(),
                "Expected error for char '{c}'"
            );
        }
    }

    #[test]
    fn test_empty_filename_rejected() {
        assert!(validate_filename("").is_err());
        assert!(validate_filename("   ").is_err());
    }
}
