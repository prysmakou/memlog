use std::path::PathBuf;
use anyhow::{bail, Result};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthType {
    None,
    ReadOnly,
    Password,
    Totp,
}

impl AuthType {
    pub fn requires_write_auth(&self) -> bool {
        matches!(self, AuthType::Password | AuthType::Totp)
    }
    pub fn is_read_only(&self) -> bool {
        *self == AuthType::ReadOnly
    }
}

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub notes_path: PathBuf,
    pub auth_type: AuthType,

    // Auth credentials (populated when auth_type is Password or Totp)
    pub username: Option<String>,
    pub password: Option<String>,
    pub secret_key: Option<String>,
    pub session_expiry_days: i64,
    pub totp_key: Option<String>,

    // Quick access panel
    pub quick_access_hide: bool,
    pub quick_access_title: String,
    pub quick_access_term: String,
    pub quick_access_sort: String,
    pub quick_access_limit: u32,

    // Path prefix
    pub path_prefix: String,
}

fn env(key: &str) -> Option<String> {
    std::env::var(key).ok().filter(|s| !s.is_empty())
}

fn env_bool(key: &str, default: bool) -> bool {
    match env(key).as_deref() {
        Some("true") | Some("True") | Some("1") | Some("yes") => true,
        Some("false") | Some("False") | Some("0") | Some("no") => false,
        _ => default,
    }
}

fn env_int(key: &str, default: i64) -> i64 {
    env(key)
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn env_uint(key: &str, default: u32) -> u32 {
    env(key)
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

impl AppConfig {
    pub fn from_env() -> Result<Self> {
        let notes_path_str = env("MEMLOG_PATH")
            .ok_or_else(|| anyhow::anyhow!("MEMLOG_PATH environment variable is required"))?;
        let notes_path = PathBuf::from(&notes_path_str);
        if !notes_path.exists() {
            bail!("MEMLOG_PATH '{}' does not exist", notes_path_str);
        }

        let auth_type = match env("MEMLOG_AUTH_TYPE").as_deref().unwrap_or("password") {
            "none" => AuthType::None,
            "read_only" => AuthType::ReadOnly,
            "password" => AuthType::Password,
            "totp" => AuthType::Totp,
            other => bail!("Unknown MEMLOG_AUTH_TYPE '{}'", other),
        };

        let path_prefix = env("MEMLOG_PATH_PREFIX").unwrap_or_default();
        if !path_prefix.is_empty() {
            if !path_prefix.starts_with('/') {
                bail!("MEMLOG_PATH_PREFIX must start with '/'");
            }
            if path_prefix.ends_with('/') {
                bail!("MEMLOG_PATH_PREFIX must not end with '/'");
            }
        }

        // Deprecated alias for quick_access_hide
        let quick_access_hide = env_bool("MEMLOG_QUICK_ACCESS_HIDE", false)
            || env_bool("MEMLOG_HIDE_RECENTLY_MODIFIED", false);

        let quick_access_sort = {
            let s = env("MEMLOG_QUICK_ACCESS_SORT").unwrap_or_else(|| "lastModified".to_string());
            if !["score", "title", "lastModified"].contains(&s.as_str()) {
                bail!("MEMLOG_QUICK_ACCESS_SORT must be one of: score, title, lastModified");
            }
            s
        };

        Ok(AppConfig {
            notes_path,
            auth_type,
            username: env("MEMLOG_USERNAME"),
            password: env("MEMLOG_PASSWORD"),
            secret_key: env("MEMLOG_SECRET_KEY"),
            session_expiry_days: env_int("MEMLOG_SESSION_EXPIRY_DAYS", 30),
            totp_key: env("MEMLOG_TOTP_KEY"),
            quick_access_hide,
            quick_access_title: env("MEMLOG_QUICK_ACCESS_TITLE")
                .unwrap_or_else(|| "RECENTLY MODIFIED".to_string()),
            quick_access_term: env("MEMLOG_QUICK_ACCESS_TERM")
                .unwrap_or_else(|| "*".to_string()),
            quick_access_sort,
            quick_access_limit: env_uint("MEMLOG_QUICK_ACCESS_LIMIT", 4),
            path_prefix,
        })
    }

    pub fn index_path(&self) -> PathBuf {
        self.notes_path.join(".memlog")
    }

    pub fn attachments_path(&self) -> PathBuf {
        self.notes_path.join("attachments")
    }
}
