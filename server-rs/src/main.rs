use std::sync::Arc;

use anyhow::Result;
use tracing_subscriber::prelude::*;

mod attachments;
mod auth;
mod config;
mod error;
mod models;
mod notes;
mod routes;
mod search;

use attachments::AttachmentStore;
use auth::AuthState;
use config::AppConfig;
use notes::NoteStore;
use search::SearchIndex;

// ── Shared state ─────────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>,
    pub auth: Arc<AuthState>,
    pub notes: Arc<NoteStore>,
    pub attachments: Arc<AttachmentStore>,
    pub search: Arc<SearchIndex>,
}

impl axum::extract::FromRef<AppState> for Arc<AuthState> {
    fn from_ref(state: &AppState) -> Self {
        state.auth.clone()
    }
}

// ── Startup ──────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = Arc::new(AppConfig::from_env()?);

    tracing::info!("Auth type: {:?}", config.auth_type);
    tracing::info!("Notes path: {}", config.notes_path.display());

    // Patch <base href=""> in index.html to match path prefix
    patch_base_href(&config.path_prefix);

    // Ensure attachments directory exists
    tokio::fs::create_dir_all(config.attachments_path()).await?;

    let auth = Arc::new(AuthState::new(config.clone()));
    let notes = Arc::new(NoteStore::new(&config.notes_path));
    let attachments = Arc::new(AttachmentStore::new(&config.notes_path));

    tracing::info!("Opening search index…");
    let search = Arc::new(
        tokio::task::spawn_blocking({
            let notes_path = config.notes_path.clone();
            let index_path = config.index_path();
            move || SearchIndex::open(notes_path, index_path)
        })
        .await??,
    );
    tracing::info!("Search index ready.");

    let state = AppState { config: config.clone(), auth, notes, attachments, search };
    let router = routes::build_router(state);

    let host = std::env::var("MEMLOG_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port = std::env::var("MEMLOG_PORT").unwrap_or_else(|_| "8080".to_string());
    let bind = format!("{host}:{port}");

    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!("Memlog server listening on {bind}");

    axum::serve(listener, router)
        .with_graceful_shutdown(async {
            tokio::signal::ctrl_c().await.unwrap();
        })
        .await?;

    Ok(())
}

fn patch_base_href(prefix: &str) {
    let index_path = std::path::Path::new("client/dist/index.html");
    if !index_path.exists() {
        return;
    }
    let Ok(content) = std::fs::read_to_string(index_path) else { return };
    let replacement = if prefix.is_empty() {
        r#"<base href="/">"#.to_string()
    } else {
        format!(r#"<base href="{prefix}/">"#)
    };
    let re = regex::Regex::new(r#"<base\s+href="[^"]*">"#).unwrap();
    let patched = re.replace(&content, replacement.as_str());
    if patched != content {
        if let Err(e) = std::fs::write(index_path, patched.as_bytes()) {
            tracing::warn!("Could not patch base href: {e}");
        }
    }
}
