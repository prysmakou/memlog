use std::sync::Arc;

use anyhow::Result;
use axum::Router;
use tracing_subscriber::prelude::*;
use rmcp::{
    ErrorData as McpError, ServerHandler,
    handler::server::{router::tool::ToolRouter, wrapper::Parameters},
    model::*,
    tool, tool_handler, tool_router,
};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use rmcp::transport::streamable_http_server::{
    StreamableHttpServerConfig, StreamableHttpService,
    session::local::LocalSessionManager,
};

// ---------------------------------------------------------------------------
// Tool parameter types
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize, JsonSchema)]
struct ListNotesParams {
    /// Sort by 'title' or 'lastModified'. Default 'lastModified'.
    #[serde(default)]
    sort: Option<String>,
    /// 'asc' or 'desc'. Default 'desc'.
    #[serde(default)]
    order: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct SearchParams {
    /// Search term. Use #tagname for tag search, "phrase" for exact match, or * for all notes.
    term: String,
    /// Sort by 'score', 'title', or 'lastModified'. Default 'score'.
    #[serde(default)]
    sort: Option<String>,
    /// 'asc' or 'desc'. Default 'desc'.
    #[serde(default)]
    order: Option<String>,
    /// Maximum number of results to return.
    #[serde(default)]
    limit: Option<i64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct NoteTitleParam {
    /// Exact note title (without .md extension).
    title: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct CreateNoteParams {
    /// Note title. Cannot contain <>:"/\|?* characters.
    title: String,
    /// Note content in Markdown.
    #[serde(default)]
    content: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct AppendParams {
    /// Exact note title (without .md extension).
    title: String,
    /// Markdown content to append.
    content: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct UpdateParams {
    /// Current note title.
    title: String,
    /// Replacement content in Markdown. Omit to keep existing.
    #[serde(default)]
    new_content: Option<String>,
    /// New title to rename the note. Omit to keep existing.
    #[serde(default)]
    new_title: Option<String>,
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct MemlogServer {
    http: reqwest::Client,
    base_url: String,
    token: Arc<RwLock<Option<String>>>,
    username: Option<String>,
    password: Option<String>,
    tool_router: ToolRouter<MemlogServer>,
}

impl MemlogServer {
    fn new() -> Self {
        Self {
            http: reqwest::Client::new(),
            base_url: std::env::var("MEMLOG_URL")
                .unwrap_or_else(|_| "http://localhost:8080".to_string())
                .trim_end_matches('/')
                .to_string(),
            token: Arc::new(RwLock::new(std::env::var("MEMLOG_TOKEN").ok())),
            username: std::env::var("MEMLOG_USERNAME").ok(),
            password: std::env::var("MEMLOG_PASSWORD").ok(),
            tool_router: Self::tool_router(),
        }
    }

    /// Return a bearer token, logging in with username/password if needed.
    async fn bearer(&self) -> Result<Option<String>, McpError> {
        {
            let guard = self.token.read().await;
            if guard.is_some() {
                return Ok(guard.clone());
            }
        }
        if let (Some(user), Some(pass)) = (&self.username, &self.password) {
            let resp = self
                .http
                .post(format!("{}/api/token", self.base_url))
                .json(&json!({"username": user, "password": pass}))
                .send()
                .await
                .map_err(|e| McpError::internal_error(e.to_string(), None))?;
            let body: Value = resp
                .json()
                .await
                .map_err(|e| McpError::internal_error(e.to_string(), None))?;
            let tok = body["access_token"]
                .as_str()
                .ok_or_else(|| {
                    McpError::internal_error("no access_token in login response", None)
                })?
                .to_string();
            *self.token.write().await = Some(tok.clone());
            Ok(Some(tok))
        } else {
            Ok(None)
        }
    }

    async fn api_get(&self, path: &str, params: &[(&str, &str)]) -> Result<Value, McpError> {
        let token = self.bearer().await?;
        let mut req = self.http.get(format!("{}{}", self.base_url, path));
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        if !params.is_empty() {
            req = req.query(params);
        }
        self.send(req).await
    }

    async fn api_post(&self, path: &str, body: Value) -> Result<Value, McpError> {
        let token = self.bearer().await?;
        let mut req = self.http.post(format!("{}{}", self.base_url, path)).json(&body);
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        self.send(req).await
    }

    async fn api_patch(&self, path: &str, body: Value) -> Result<Value, McpError> {
        let token = self.bearer().await?;
        let mut req = self.http.patch(format!("{}{}", self.base_url, path)).json(&body);
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        self.send(req).await
    }

    async fn api_delete(&self, path: &str) -> Result<(), McpError> {
        let token = self.bearer().await?;
        let mut req = self.http.delete(format!("{}{}", self.base_url, path));
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        let resp = req
            .send()
            .await
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(McpError::internal_error(format!("HTTP {status}: {body}"), None));
        }
        Ok(())
    }

    async fn send(&self, req: reqwest::RequestBuilder) -> Result<Value, McpError> {
        let resp = req
            .send()
            .await
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(McpError::internal_error(format!("HTTP {status}: {body}"), None));
        }
        resp.json()
            .await
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    fn text(value: &Value) -> Result<CallToolResult, McpError> {
        Ok(CallToolResult::success(vec![Content::text(
            serde_json::to_string_pretty(value).unwrap_or_default(),
        )]))
    }
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

#[tool_router]
impl MemlogServer {
    #[tool(description = "List all notes with title and lastModified timestamp (no content).")]
    async fn list_notes(
        &self,
        Parameters(p): Parameters<ListNotesParams>,
    ) -> Result<CallToolResult, McpError> {
        let sort = p.sort.unwrap_or_else(|| "lastModified".to_string());
        let order = p.order.unwrap_or_else(|| "desc".to_string());
        let data = self
            .api_get("/api/search", &[("term", "*"), ("sort", &sort), ("order", &order)])
            .await?;
        let notes: Vec<Value> = data
            .as_array()
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(|n| json!({"title": n["title"], "lastModified": n["lastModified"]}))
            .collect();
        Self::text(&json!(notes))
    }

    #[tool(description = "Search notes by keyword, phrase, or #tag. Use * for all notes.")]
    async fn search_notes(
        &self,
        Parameters(p): Parameters<SearchParams>,
    ) -> Result<CallToolResult, McpError> {
        let term = p.term;
        let sort = p.sort.unwrap_or_else(|| "score".to_string());
        let order = p.order.unwrap_or_else(|| "desc".to_string());
        let limit_str = p.limit.map(|l| l.to_string());
        let mut params: Vec<(&str, &str)> =
            vec![("term", &term), ("sort", &sort), ("order", &order)];
        if let Some(ref l) = limit_str {
            params.push(("limit", l));
        }
        let data = self.api_get("/api/search", &params).await?;
        Self::text(&data)
    }

    #[tool(description = "Get the full content of a note by title.")]
    async fn get_note(
        &self,
        Parameters(p): Parameters<NoteTitleParam>,
    ) -> Result<CallToolResult, McpError> {
        let data = self.api_get(&format!("/api/notes/{}", p.title), &[]).await?;
        Self::text(&data)
    }

    #[tool(description = "Create a new note.")]
    async fn create_note(
        &self,
        Parameters(p): Parameters<CreateNoteParams>,
    ) -> Result<CallToolResult, McpError> {
        let data = self
            .api_post(
                "/api/notes",
                json!({"title": p.title, "content": p.content.unwrap_or_default()}),
            )
            .await?;
        Self::text(&data)
    }

    #[tool(
        description = "Append content to the end of an existing note. Safer than update_note — existing content is never overwritten."
    )]
    async fn append_to_note(
        &self,
        Parameters(p): Parameters<AppendParams>,
    ) -> Result<CallToolResult, McpError> {
        let existing = self.api_get(&format!("/api/notes/{}", p.title), &[]).await?;
        let current = existing["content"].as_str().unwrap_or("");
        let separator = if current.ends_with('\n') { "\n" } else { "\n\n" };
        let new_content = format!("{current}{separator}{}", p.content);
        let data = self
            .api_patch(
                &format!("/api/notes/{}", p.title),
                json!({"newContent": new_content}),
            )
            .await?;
        Self::text(&data)
    }

    #[tool(description = "Update an existing note's content or title.")]
    async fn update_note(
        &self,
        Parameters(p): Parameters<UpdateParams>,
    ) -> Result<CallToolResult, McpError> {
        let mut body = serde_json::Map::new();
        if let Some(c) = p.new_content {
            body.insert("newContent".into(), json!(c));
        }
        if let Some(t) = p.new_title {
            body.insert("newTitle".into(), json!(t));
        }
        let data = self
            .api_patch(&format!("/api/notes/{}", p.title), Value::Object(body))
            .await?;
        Self::text(&data)
    }

    #[tool(description = "Delete a note permanently.")]
    async fn delete_note(
        &self,
        Parameters(p): Parameters<NoteTitleParam>,
    ) -> Result<CallToolResult, McpError> {
        self.api_delete(&format!("/api/notes/{}", p.title)).await?;
        Ok(CallToolResult::success(vec![Content::text(format!(
            "Deleted '{}'.",
            p.title
        ))]))
    }

    #[tool(description = "Return all tags currently used across notes.")]
    async fn list_tags(&self) -> Result<CallToolResult, McpError> {
        let data = self.api_get("/api/tags", &[]).await?;
        Self::text(&data)
    }
}

// ---------------------------------------------------------------------------
// ServerHandler
// ---------------------------------------------------------------------------

#[tool_handler]
impl ServerHandler for MemlogServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::from_build_env())
            .with_instructions(
                "Read and write Memlog notes over HTTP. \
                 Tools: list_notes, search_notes, get_note, create_note, \
                 append_to_note, update_note, delete_note, list_tags."
                    .to_string(),
            )
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".to_string().into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let bind = std::env::var("MCP_BIND").unwrap_or_else(|_| "0.0.0.0:8090".to_string());
    let ct = CancellationToken::new();

    let service = StreamableHttpService::new(
        || Ok(MemlogServer::new()),
        LocalSessionManager::default().into(),
        StreamableHttpServerConfig {
            cancellation_token: ct.child_token(),
            ..Default::default()
        },
    );

    let router = Router::new().nest_service("/mcp", service);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!("Memlog MCP server listening on {bind}");

    axum::serve(listener, router)
        .with_graceful_shutdown(async move {
            tokio::signal::ctrl_c().await.unwrap();
            ct.cancel();
        })
        .await?;

    Ok(())
}
