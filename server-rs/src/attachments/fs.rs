use std::path::{Path, PathBuf};

use axum::extract::Multipart;
use chrono::Utc;

use crate::error::{validate_filename, AppError};
use crate::models::AttachmentCreateResponse;

pub struct AttachmentStore {
    base_path: PathBuf,
    storage_path: PathBuf,
}

impl AttachmentStore {
    pub fn new(notes_path: impl Into<PathBuf>) -> Self {
        let base_path: PathBuf = notes_path.into();
        let storage_path = base_path.join("attachments");
        Self { base_path, storage_path }
    }

    pub fn storage_path(&self) -> &Path {
        &self.storage_path
    }

    pub async fn ensure_dir(&self) -> Result<(), AppError> {
        tokio::fs::create_dir_all(&self.storage_path)
            .await
            .map_err(|e| AppError::Internal(e.into()))
    }

    pub async fn create(&self, mut multipart: Multipart) -> Result<AttachmentCreateResponse, AppError> {
        self.ensure_dir().await?;

        let field = multipart
            .next_field()
            .await
            .map_err(|e| AppError::BadRequest(e.to_string()))?
            .ok_or_else(|| AppError::BadRequest("No file field in request".to_string()))?;

        let original_name = field
            .file_name()
            .map(|s| s.to_string())
            .or_else(|| field.name().map(|s| s.to_string()))
            .unwrap_or_else(|| "upload".to_string());

        validate_filename(&original_name)?;

        let data = field
            .bytes()
            .await
            .map_err(|e| AppError::Internal(anyhow::anyhow!(e)))?;

        let final_name = self.save_file(&original_name, &data).await?;
        let url = format!("attachments/{}", urlencoded(&final_name));

        Ok(AttachmentCreateResponse { filename: final_name, url })
    }

    async fn save_file(&self, name: &str, data: &[u8]) -> Result<String, AppError> {
        let p = self.storage_path.join(name);
        if !p.exists() {
            tokio::fs::write(&p, data)
                .await
                .map_err(|e| AppError::Internal(e.into()))?;
            return Ok(name.to_string());
        }
        // Collision — add timestamp suffix
        let suffixed = timestamp_filename(name);
        tokio::fs::write(self.storage_path.join(&suffixed), data)
            .await
            .map_err(|e| AppError::Internal(e.into()))?;
        Ok(suffixed)
    }

    pub fn path_for(&self, filename: &str) -> Result<PathBuf, AppError> {
        validate_filename(filename)?;
        let p = self.storage_path.join(filename);
        if !p.exists() {
            return Err(AppError::AttachmentNotFound);
        }
        Ok(p)
    }

    /// Relative URL base used for links embedded in notes.
    pub fn _base_path(&self) -> &Path {
        &self.base_path
    }
}

fn timestamp_filename(name: &str) -> String {
    let ts = Utc::now().format("%Y-%m-%dT%H-%M-%SZ");
    match name.rsplit_once('.') {
        Some((stem, ext)) => format!("{stem}_{ts}.{ext}"),
        None => format!("{name}_{ts}"),
    }
}

fn urlencoded(s: &str) -> String {
    s.chars()
        .flat_map(|c| {
            if c.is_alphanumeric() || "-_.~".contains(c) {
                vec![c.to_string()]
            } else {
                format!("%{:02X}", c as u32)
                    .chars()
                    .map(|x| x.to_string())
                    .collect()
            }
        })
        .collect()
}
