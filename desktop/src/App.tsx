import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { isLocaleCode, useI18n, type LocaleCode } from "./i18n";
import "./App.css";

type Tab = "new" | "history" | "settings";

type Source = { qa_id?: number; score?: number };

type ConversationMessage = {
  id: number;
  role: string;
  content: string;
  created_at?: string;
};

type Conversation = {
  id: number;
  title: string;
  status: string;
  status_label?: string;
  updated_at?: string;
  turn_count?: number;
  messages?: ConversationMessage[];
};

type ModelOption = {
  id: string;
  display_name?: string;
  description?: string;
  kind?: string;
};

type Settings = {
  has_api_key?: boolean;
  company_name?: string;
  greeting?: string;
  extra_instructions?: string;
  banned_phrases?: string;
  reply_model?: string;
  embedding_model?: string;
  reply_models?: ModelOption[];
  embedding_models?: ModelOption[];
  models_fetched_at?: string | null;
  rag_min_score?: number;
  mask_email?: boolean;
  mask_phone?: boolean;
  mask_address?: boolean;
  mask_name?: boolean;
  mask_order_id?: boolean;
  use_graph_rag?: boolean;
  graph_search_mode?: string;
  ai_provider?: string;
  embedding_provider?: string;
  openai_base_url?: string;
  claude_base_url?: string;
  ollama_base_url?: string;
  ollama_model?: string;
  ui_locale?: string;
  faq_snapshot?: { question: string; answer: string; problem?: string }[] | string;
  staff_addresses?: string[];
  staff_domains?: string[];
  stats?: {
    messages?: number;
    conversations?: number;
    qa?: number;
    last_import_at?: string | null;
  };
  graph?: {
    entity_count?: number;
    relation_count?: number;
    by_type?: Record<string, number>;
    last_build?: { completed_at?: string; qa_processed?: number } | null;
  };
  knowledge?: {
    qa_total?: number;
    qa_verified?: number;
    products?: number;
    problems?: number;
    qa_without_graph_link?: number;
    coverage_ratio?: number;
  };
  progress?: { stage?: string; percent?: number };
};

type ImportRow = {
  id: number;
  source_type: string;
  filename: string;
  status: string;
  total_messages: number;
  new_messages: number;
  duplicate_messages: number;
  qa_count: number;
  completed_at?: string | null;
};

const SIDECAR_URL = "http://127.0.0.1:18765";
const APP_VERSION = "0.01";

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function sidecar<T = Record<string, unknown>>(
  action: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const body = { action, ...payload };
  if (isTauri()) {
    return await invoke<T>("sidecar_request", { payload: body });
  }
  const response = await fetch(SIDECAR_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Sidecar HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

async function reconnectEngine(): Promise<void> {
  if (isTauri()) {
    await invoke("restart_sidecar");
    return;
  }
  await fetch(`${SIDECAR_URL}/health`);
}

export default function App() {
  const { t, locale, setLocale, locales } = useI18n();
  const [tab, setTab] = useState<Tab>("history");
  const [sidecarOk, setSidecarOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // New / result
  const [mailText, setMailText] = useState("");
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [insufficient, setInsufficient] = useState(false);

  // History
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [followupText, setFollowupText] = useState("");

  // Settings
  const [settings, setSettings] = useState<Settings>({});
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importType, setImportType] = useState("maildealer_csv");
  const [imports, setImports] = useState<ImportRow[]>([]);
  const [faqs, setFaqs] = useState<{ question: string; answer: string; problem?: string }[]>([]);
  const [openaiKeyInput, setOpenaiKeyInput] = useState("");
  const [claudeKeyInput, setClaudeKeyInput] = useState("");
  const [workspaceFile, setWorkspaceFile] = useState<File | null>(null);
  const [graphTrends, setGraphTrends] = useState<
    { entity_type: string; name: string; mentions: number }[]
  >([]);
  const [staffAddresses, setStaffAddresses] = useState("support@example.com");
  const [staffDomains, setStaffDomains] = useState("example.com");

  const replyModelOptions = useMemo(() => {
    const list = settings.reply_models || [];
    const current = settings.reply_model;
    if (current && !list.some((m) => m.id === current)) {
      return [{ id: current, display_name: current }, ...list];
    }
    return list;
  }, [settings.reply_models, settings.reply_model]);

  async function refreshHealth() {
    try {
      if (isTauri()) {
        const res = await invoke<{ success: boolean }>("sidecar_health");
        setSidecarOk(!!res.success);
      } else {
        const res = await sidecar<{ success: boolean }>("health");
        setSidecarOk(!!res.success);
      }
      setError(null);
    } catch {
      setSidecarOk(false);
      setError(t("engine.connectFailed"));
    }
  }

  async function loadSettings() {
    const res = await sidecar<{ success: boolean; settings: Settings }>("get_settings");
    if (res.success) {
      setSettings(res.settings);
      if (isLocaleCode(res.settings.ui_locale)) {
        setLocale(res.settings.ui_locale);
      }
      const addrs = res.settings.staff_addresses || [];
      const domains = res.settings.staff_domains || [];
      if (addrs.length) setStaffAddresses(addrs.join(", "));
      if (domains.length) setStaffDomains(domains.join(", "));
    }
  }

  async function changeLocale(next: LocaleCode) {
    setLocale(next);
    setSettings((prev) => ({ ...prev, ui_locale: next }));
    try {
      await sidecar("save_settings", { settings: { ui_locale: next } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function loadConversations(query?: string) {
    const res = await sidecar<{ success: boolean; conversations: Conversation[] }>(
      "list_conversations",
      { query: query ?? historyQuery },
    );
    if (res.success) setConversations(res.conversations || []);
  }

  async function loadImports() {
    const res = await sidecar<{ success: boolean; imports: ImportRow[] }>("list_imports");
    if (res.success) setImports(res.imports || []);
  }

  async function loadGraphInfo() {
    const res = await sidecar<{
      success: boolean;
      graph?: Settings["graph"];
      trends?: { entity_type: string; name: string; mentions: number }[];
    }>("graph_stats");
    if (res.success) {
      setSettings((prev) => ({ ...prev, graph: res.graph }));
      setGraphTrends(res.trends || []);
    }
  }

  useEffect(() => {
    refreshHealth();
    loadSettings().catch(() => undefined);
    loadConversations().catch(() => undefined);
    const id = window.setInterval(() => {
      refreshHealth();
    }, 5000);
    return () => window.clearInterval(id);
  }, []);

  async function onGenerateNew() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{
        success: boolean;
        error?: string;
        conversation?: Conversation;
        sources?: Source[];
        insufficient_evidence?: boolean;
      }>("generate_reply", { content: mailText });
      if (!res.success) throw new Error(res.error || t("errors.generateFailed"));
      setActiveConversation(res.conversation || null);
      setSources(res.sources || []);
      setInsufficient(!!res.insufficient_evidence);
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateFollowup() {
    if (!activeConversation) return;
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{
        success: boolean;
        error?: string;
        conversation?: Conversation;
        sources?: Source[];
        insufficient_evidence?: boolean;
      }>("generate_reply", {
        conversation_id: activeConversation.id,
        content: followupText,
      });
      if (!res.success) throw new Error(res.error || t("errors.generateFailed"));
      setActiveConversation(res.conversation || null);
      setSources(res.sources || []);
      setInsufficient(!!res.insufficient_evidence);
      setFollowupText("");
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function openConversation(id: number) {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; conversation: Conversation }>(
        "get_conversation",
        { conversation_id: id },
      );
      setActiveConversation(res.conversation);
      setSources([]);
      setTab("history");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copyText(text: string) {
    await navigator.clipboard.writeText(text);
  }

  async function saveApiKey() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; error?: string }>("set_api_key", {
        api_key: apiKeyInput,
      });
      if (!res.success) throw new Error(res.error || t("errors.saveFailed"));
      setApiKeyInput("");
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function testApiKey() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; error?: string; message?: string }>(
        "test_api_key",
      );
      if (!res.success) throw new Error(res.error || t("errors.connectionTestFailed"));
      alert(t("alerts.connectionOk"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function refreshModels() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{
        success: boolean;
        error?: string;
        reply_models?: ModelOption[];
        embedding_models?: ModelOption[];
        models_fetched_at?: string;
        reply_model?: string;
      }>("refresh_models");
      if (!res.success) throw new Error(res.error || t("errors.modelsFetchFailed"));
      setSettings((prev) => ({
        ...prev,
        reply_models: res.reply_models || [],
        embedding_models: res.embedding_models || [],
        models_fetched_at: res.models_fetched_at || null,
        reply_model: res.reply_model || prev.reply_model,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function selectReplyModel(modelId: string) {
    setSettings((prev) => ({ ...prev, reply_model: modelId }));
    setBusy(true);
    setError(null);
    try {
      await sidecar("save_settings", { settings: { reply_model: modelId } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveAnswerSettings() {
    setBusy(true);
    try {
      await sidecar("save_settings", {
        settings: {
          company_name: settings.company_name || "",
          greeting: settings.greeting || "",
          extra_instructions: settings.extra_instructions || "",
          banned_phrases: settings.banned_phrases || "",
          reply_model: settings.reply_model || "gemini-2.0-flash",
          embedding_model: settings.embedding_model || "text-embedding-004",
          rag_min_score: Number(settings.rag_min_score ?? 0.25),
          mask_email: settings.mask_email ?? true,
          mask_phone: settings.mask_phone ?? true,
          mask_address: settings.mask_address ?? true,
          mask_name: settings.mask_name ?? false,
          mask_order_id: settings.mask_order_id ?? false,
          use_graph_rag: settings.use_graph_rag ?? true,
          graph_search_mode: settings.graph_search_mode || "local",
          ai_provider: settings.ai_provider || "gemini",
          embedding_provider: settings.embedding_provider || settings.ai_provider || "gemini",
          openai_base_url: settings.openai_base_url || "https://api.openai.com/v1",
          claude_base_url: settings.claude_base_url || "https://api.anthropic.com",
          ollama_base_url: settings.ollama_base_url || "http://127.0.0.1:11434",
          ollama_model: settings.ollama_model || "llama3.2",
          ui_locale: locale,
          staff_addresses: staffAddresses
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          staff_domains: staffDomains
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
      });
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rebuildRag() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success?: boolean; error?: string; embedded?: number }>(
        "rebuild_rag",
      );
      if (res.success === false) throw new Error(res.error || t("errors.ragRebuildFailed"));
      alert(t("alerts.ragRebuilt", { n: res.embedded ?? 0 }));
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rebuildGraph() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{
        success: boolean;
        error?: string;
        entity_count?: number;
        relation_count?: number;
        graph?: Settings["graph"];
        trends?: { entity_type: string; name: string; mentions: number }[];
      }>("rebuild_graph");
      if (!res.success) throw new Error(res.error || t("errors.graphRebuildFailed"));
      setSettings((prev) => ({ ...prev, graph: res.graph }));
      setGraphTrends(res.trends || []);
      alert(t("alerts.graphRebuilt", { entities: res.entity_count ?? 0, relations: res.relation_count ?? 0 }));
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateFaqs() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{
        success: boolean;
        error?: string;
        faqs?: { question: string; answer: string; problem?: string }[];
      }>("generate_faqs", { limit: 20 });
      if (!res.success) throw new Error(res.error || t("errors.faqFailed"));
      setFaqs(res.faqs || []);
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportWorkspace() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; error?: string; path?: string }>(
        "export_workspace",
      );
      if (!res.success) throw new Error(res.error || t("errors.exportFailed"));
      alert(t("alerts.workspaceExported", { path: res.path || "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importWorkspaceZip() {
    if (!workspaceFile) {
      setError(t("errors.selectWorkspaceZip"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const content_base64 = await fileToBase64(workspaceFile);
      const res = await sidecar<{ success: boolean; error?: string }>("import_workspace", {
        filename: workspaceFile.name,
        content_base64,
      });
      if (!res.success) throw new Error(res.error || t("errors.importFailed"));
      setWorkspaceFile(null);
      await loadSettings();
      await loadImports();
      await loadGraphInfo();
      alert(t("alerts.workspaceImported"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveOpenaiKey() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; error?: string }>("set_openai_api_key", {
        api_key: openaiKeyInput,
      });
      if (!res.success) throw new Error(res.error || t("errors.saveFailed"));
      setOpenaiKeyInput("");
      alert(t("alerts.openaiKeySaved"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveClaudeKey() {
    setBusy(true);
    setError(null);
    try {
      const res = await sidecar<{ success: boolean; error?: string }>("set_claude_api_key", {
        api_key: claudeKeyInput,
      });
      if (!res.success) throw new Error(res.error || t("errors.saveFailed"));
      setClaudeKeyInput("");
      alert(t("alerts.claudeKeySaved"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function fileToBase64(file: File): Promise<string> {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(reader.error || new Error(t("errors.fileReadFailed")));
      reader.readAsDataURL(file);
    });
  }

  async function runImport() {
    if (!importFile) {
      setError(t("errors.selectImportFile"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const content_base64 = await fileToBase64(importFile);
      const res = await sidecar<{
        success: boolean;
        error?: string;
        new_messages?: number;
        duplicate_messages?: number;
        qa_count?: number;
      }>("import_mail", {
        source_type: importType,
        filename: importFile.name,
        content_base64,
      });
      if (!res.success) throw new Error(res.error || t("errors.importMailFailed"));
      alert(
        t("alerts.importDone", {
          added: res.new_messages ?? 0,
          dup: res.duplicate_messages ?? 0,
          qa: res.qa_count ?? 0,
        }),
      );
      setImportFile(null);
      await loadSettings();
      await loadImports();
      await loadGraphInfo();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>{t("app.title")}</h1>
          <p className="sub">{t("app.subtitle")}</p>
        </div>
        <div className={`badge ${sidecarOk ? "ok" : "ng"}`}>
          {sidecarOk === null
            ? t("engine.checking")
            : sidecarOk
              ? t("engine.connected")
              : t("engine.disconnected")}
        </div>
      </header>

      <nav className="tabs">
        <button
          className={tab === "history" ? "active" : ""}
          onClick={() => {
            setTab("history");
            loadConversations().catch(() => undefined);
          }}
        >
          {t("nav.history")}
        </button>
        <button className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>
          {t("nav.new")}
        </button>
        <button
          className={tab === "settings" ? "active" : ""}
          onClick={() => {
            setTab("settings");
            loadSettings().catch(() => undefined);
            loadImports().catch(() => undefined);
            loadGraphInfo().catch(() => undefined);
          }}
        >
          {t("nav.settings")}
        </button>
      </nav>

      {error && (
        <div className="error">
          <span>{error}</span>
          <button
            onClick={() => {
              reconnectEngine()
                .then(() => refreshHealth())
                .catch(() => refreshHealth());
            }}
          >
            {t("engine.reconnect")}
          </button>
        </div>
      )}

      {tab === "new" && (
        <section className="panel">
          {!activeConversation ? (
            <>
              <h2>{t("new.heading")}</h2>
              <label>{t("new.mailLabel")}</label>
              <textarea
                value={mailText}
                onChange={(e) => setMailText(e.target.value)}
                placeholder={t("new.mailPlaceholder")}
                rows={14}
              />
              <div className="actions">
                <button disabled={busy || !mailText.trim()} onClick={onGenerateNew}>
                  {busy ? t("new.generating") : t("new.generate")}
                </button>
              </div>
            </>
          ) : (
            <ConversationView
              conversation={activeConversation}
              sources={sources}
              insufficient={insufficient}
              onCopy={copyText}
              onReset={() => {
                setActiveConversation(null);
                setMailText("");
                setSources([]);
                setInsufficient(false);
              }}
            />
          )}
        </section>
      )}

      {tab === "history" && (
        <section className="panel history">
          <div className="list">
            <h2>{t("history.heading")}</h2>
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder={t("history.searchPlaceholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter") loadConversations(historyQuery).catch(() => undefined);
              }}
            />
            <div className="actions" style={{ marginTop: 8 }}>
              <button
                disabled={busy}
                onClick={() => loadConversations(historyQuery).catch(() => undefined)}
              >
                {t("history.search")}
              </button>
            </div>
            {conversations.length === 0 && <p className="muted">{t("history.empty")}</p>}
            {conversations.map((c) => (
              <button key={c.id} className="conv-item" onClick={() => openConversation(c.id)}>
                <strong>{c.title}</strong>
                <span>
                  {t("history.updated", { time: c.updated_at || "-", turns: c.turn_count || 0 })}
                </span>
                <em>{c.status_label || c.status}</em>
              </button>
            ))}
          </div>
          <div className="detail">
            {activeConversation ? (
              <>
                <ConversationView
                  conversation={activeConversation}
                  sources={sources}
                  insufficient={insufficient}
                  onCopy={copyText}
                />
                <div className="followup">
                  <h3>{t("history.followupHeading")}</h3>
                  <textarea
                    rows={6}
                    value={followupText}
                    onChange={(e) => setFollowupText(e.target.value)}
                    placeholder={t("history.followupPlaceholder")}
                  />
                  <button disabled={busy || !followupText.trim()} onClick={onGenerateFollowup}>
                    {busy ? t("new.generating") : t("new.generate")}
                  </button>
                </div>
              </>
            ) : (
              <p className="muted">{t("history.selectPrompt")}</p>
            )}
          </div>
        </section>
      )}

      {tab === "settings" && (
        <section className="panel settings">
          <h2>{t("settings.languageHeading")}</h2>
          <p className="muted">{t("settings.languageHint")}</p>
          <label>{t("settings.language")}</label>
          <select
            value={locale}
            onChange={(e) => changeLocale(e.target.value as LocaleCode)}
          >
            {locales.map((l) => (
              <option key={l.code} value={l.code}>
                {l.nativeLabel}
              </option>
            ))}
          </select>

          <h2>{t("settings.aiHeading")}</h2>
          <p className="muted">{t("settings.apiKeyHint")}</p>
          <label>{t("settings.aiProvider")}</label>
          <select
            value={settings.ai_provider || "gemini"}
            onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}
          >
            <option value="gemini">{t("settings.providerGemini")}</option>
            <option value="openai">{t("settings.providerOpenai")}</option>
            <option value="claude">{t("settings.providerClaude")}</option>
            <option value="ollama">{t("settings.providerOllama")}</option>
          </select>
          {(settings.ai_provider || "gemini") === "gemini" && (
            <>
              <label>
                {t("settings.geminiKey")}{" "}
                {settings.has_api_key ? t("settings.configured") : t("settings.notConfigured")}
              </label>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="AIza..."
              />
              <div className="actions">
                <button disabled={busy || !apiKeyInput} onClick={saveApiKey}>
                  {t("settings.save")}
                </button>
                <button disabled={busy} onClick={testApiKey}>
                  {t("settings.testConnection")}
                </button>
                <button disabled={busy || !settings.has_api_key} onClick={refreshModels}>
                  {t("settings.fetchModels")}
                </button>
              </div>
            </>
          )}
          {settings.ai_provider === "openai" && (
            <>
              <label>{t("settings.openaiKey")}</label>
              <input
                type="password"
                value={openaiKeyInput}
                onChange={(e) => setOpenaiKeyInput(e.target.value)}
                placeholder="sk-..."
              />
              <label>{t("settings.openaiBaseUrl")}</label>
              <input
                value={settings.openai_base_url || "https://api.openai.com/v1"}
                onChange={(e) => setSettings({ ...settings, openai_base_url: e.target.value })}
              />
              <div className="actions">
                <button disabled={busy || !openaiKeyInput} onClick={saveOpenaiKey}>
                  {t("settings.saveKey")}
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    sidecar("refresh_provider_models")
                      .then(() => loadSettings())
                      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
                  }
                >
                  {t("settings.fetchModels")}
                </button>
              </div>
            </>
          )}
          {settings.ai_provider === "claude" && (
            <>
              <label>{t("settings.claudeKey")}</label>
              <input
                type="password"
                value={claudeKeyInput}
                onChange={(e) => setClaudeKeyInput(e.target.value)}
                placeholder="sk-ant-..."
              />
              <label>{t("settings.claudeBaseUrl")}</label>
              <input
                value={settings.claude_base_url || "https://api.anthropic.com"}
                onChange={(e) => setSettings({ ...settings, claude_base_url: e.target.value })}
              />
              <p className="muted">{t("settings.claudeEmbeddingHint")}</p>
              <div className="actions">
                <button disabled={busy || !claudeKeyInput} onClick={saveClaudeKey}>
                  {t("settings.saveKey")}
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    sidecar("refresh_provider_models")
                      .then(async (res) => {
                        const r = res as { success?: boolean; error?: string };
                        if (r.success === false) throw new Error(r.error || t("errors.modelsFetchShort"));
                        await loadSettings();
                      })
                      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
                  }
                >
                  {t("settings.fetchModels")}
                </button>
              </div>
            </>
          )}
          {settings.ai_provider === "ollama" && (
            <>
              <label>{t("settings.ollamaBaseUrl")}</label>
              <input
                value={settings.ollama_base_url || "http://127.0.0.1:11434"}
                onChange={(e) => setSettings({ ...settings, ollama_base_url: e.target.value })}
              />
              <label>{t("settings.ollamaModel")}</label>
              <input
                value={settings.ollama_model || "llama3.2"}
                onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
              />
              <div className="actions">
                <button
                  disabled={busy}
                  onClick={() =>
                    sidecar("refresh_provider_models")
                      .then(async (res) => {
                        const r = res as { success?: boolean; error?: string };
                        if (r.success === false) throw new Error(r.error || t("errors.modelsFetchShort"));
                        await loadSettings();
                      })
                      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
                  }
                >
                  {t("settings.fetchModels")}
                </button>
              </div>
            </>
          )}

          <label>{t("settings.replyModel")}</label>
          <select
            value={settings.reply_model || ""}
            onChange={(e) => selectReplyModel(e.target.value)}
            disabled={!replyModelOptions.length}
          >
            {!replyModelOptions.length && (
              <option value="">{t("settings.fetchModelsFirst")}</option>
            )}
            {replyModelOptions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name && m.display_name !== m.id
                  ? `${m.display_name} (${m.id})`
                  : m.id}
              </option>
            ))}
          </select>
          <p className="muted">
            {settings.models_fetched_at
              ? t("settings.modelsFetchedAt", { at: settings.models_fetched_at })
              : t("settings.modelsNotFetched")}
          </p>
          <label>{t("settings.embeddingModel")}</label>
          {settings.embedding_models && settings.embedding_models.length > 0 ? (
            <select
              value={settings.embedding_model || ""}
              onChange={(e) => {
                const value = e.target.value;
                setSettings({ ...settings, embedding_model: value });
                sidecar("save_settings", { settings: { embedding_model: value } }).catch(
                  (err) => setError(err instanceof Error ? err.message : String(err)),
                );
              }}
            >
              {(settings.embedding_models || []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name && m.display_name !== m.id
                    ? `${m.display_name} (${m.id})`
                    : m.id}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={settings.embedding_model || ""}
              onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })}
              placeholder="text-embedding-004"
            />
          )}

          <h2>{t("settings.answerHeading")}</h2>
          <label>{t("settings.companyName")}</label>
          <input
            value={settings.company_name || ""}
            onChange={(e) => setSettings({ ...settings, company_name: e.target.value })}
          />
          <label>{t("settings.greeting")}</label>
          <input
            value={settings.greeting || ""}
            onChange={(e) => setSettings({ ...settings, greeting: e.target.value })}
          />
          <label>{t("settings.extraInstructions")}</label>
          <textarea
            rows={4}
            value={settings.extra_instructions || ""}
            onChange={(e) => setSettings({ ...settings, extra_instructions: e.target.value })}
          />
          <label>{t("settings.bannedPhrases")}</label>
          <textarea
            rows={3}
            value={settings.banned_phrases || ""}
            onChange={(e) => setSettings({ ...settings, banned_phrases: e.target.value })}
          />
          <label>{t("settings.staffAddresses")}</label>
          <input value={staffAddresses} onChange={(e) => setStaffAddresses(e.target.value)} />
          <label>{t("settings.staffDomains")}</label>
          <input value={staffDomains} onChange={(e) => setStaffDomains(e.target.value)} />

          <h3>{t("settings.maskHeading")}</h3>
          <div className="checks">
            {(
              [
                ["mask_email", "settings.maskEmail"],
                ["mask_phone", "settings.maskPhone"],
                ["mask_address", "settings.maskAddress"],
                ["mask_name", "settings.maskName"],
                ["mask_order_id", "settings.maskOrderId"],
              ] as const
            ).map(([key, labelKey]) => (
              <label key={key} className="check">
                <input
                  type="checkbox"
                  checked={Boolean(settings[key] ?? (key !== "mask_name" && key !== "mask_order_id"))}
                  onChange={(e) => setSettings({ ...settings, [key]: e.target.checked })}
                />
                <span>{t(labelKey)}</span>
              </label>
            ))}
          </div>
          <div className="checks">
            <label className="check">
              <input
                type="checkbox"
                checked={settings.use_graph_rag ?? true}
                onChange={(e) => setSettings({ ...settings, use_graph_rag: e.target.checked })}
              />
              <span>{t("settings.useGraphRag")}</span>
            </label>
          </div>
          <label>{t("settings.graphSearchMode")}</label>
          <select
            value={settings.graph_search_mode || "local"}
            onChange={(e) => setSettings({ ...settings, graph_search_mode: e.target.value })}
          >
            <option value="local">Local</option>
            <option value="global">Global</option>
            <option value="drift">DRIFT</option>
          </select>
          <div className="actions">
            <button disabled={busy} onClick={saveAnswerSettings}>
              {t("settings.saveSettings")}
            </button>
          </div>

          <h2>{t("settings.ragHeading")}</h2>
          <div className="stats">
            <div>{t("settings.statMessages", { n: settings.stats?.messages ?? 0 })}</div>
            <div>{t("settings.statConversations", { n: settings.stats?.conversations ?? 0 })}</div>
            <div>{t("settings.statQa", { n: settings.stats?.qa ?? 0 })}</div>
            <div>{t("settings.statLastImport", { at: settings.stats?.last_import_at || "-" })}</div>
          </div>
          <label>{t("settings.dataFormat")}</label>
          <select value={importType} onChange={(e) => setImportType(e.target.value)}>
            <option value="maildealer_csv">Mail Dealer CSV</option>
            <option value="maildealer_mbox">Mail Dealer MBOX</option>
            <option value="mbox">Generic MBOX</option>
            <option value="thunderbird">Thunderbird MBOX</option>
            <option value="eml">EML</option>
            <option value="csv">Generic CSV</option>
            <option value="gmail_mbox">Gmail MBOX</option>
            <option value="outlook_csv">Outlook CSV</option>
            <option value="zendesk_csv">Zendesk CSV</option>
          </select>
          <label>{t("settings.file")}</label>
          <input
            key={`${importType}-${importFile?.name || "empty"}`}
            type="file"
            accept={
              importType.includes("csv")
                ? ".csv,text/csv"
                : importType === "eml"
                  ? ".eml,message/rfc822"
                  : ".mbox,.mbx,application/mbox,text/plain"
            }
            onChange={(e) => setImportFile(e.target.files?.[0] || null)}
          />
          <p className="muted">
            {importFile
              ? t("settings.fileSelected", {
                  name: importFile.name,
                  kb: Math.max(1, Math.round(importFile.size / 1024)),
                })
              : t("settings.fileHint")}
          </p>
          <div className="actions">
            <button disabled={busy || !importFile} onClick={runImport}>
              {busy ? t("settings.importing") : t("settings.addData")}
            </button>
            <button disabled={busy} onClick={rebuildRag}>
              {t("settings.rebuildRag")}
            </button>
            <button disabled={busy} onClick={rebuildGraph}>
              {t("settings.rebuildGraph")}
            </button>
            <button disabled={busy} onClick={generateFaqs}>
              {t("settings.generateFaq")}
            </button>
            <button disabled={busy} onClick={exportWorkspace}>
              {t("settings.workspaceExport")}
            </button>
          </div>
          <label>{t("settings.workspaceImportLabel")}</label>
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => setWorkspaceFile(e.target.files?.[0] || null)}
          />
          <div className="actions">
            <button disabled={busy || !workspaceFile} onClick={importWorkspaceZip}>
              {t("settings.workspaceImport")}
            </button>
          </div>
          <p className="muted">{t("settings.sampleHint")}</p>

          <h3>{t("settings.graphHeading")}</h3>
          <div className="stats">
            <div>{t("settings.statEntity", { n: settings.graph?.entity_count ?? 0 })}</div>
            <div>{t("settings.statRelation", { n: settings.graph?.relation_count ?? 0 })}</div>
            <div>{t("settings.statProduct", { n: settings.graph?.by_type?.product ?? 0 })}</div>
            <div>{t("settings.statProblem", { n: settings.graph?.by_type?.problem ?? 0 })}</div>
            <div>{t("settings.statCause", { n: settings.graph?.by_type?.cause ?? 0 })}</div>
            <div>{t("settings.statAction", { n: settings.graph?.by_type?.action ?? 0 })}</div>
          </div>
          <p className="muted">
            {t("settings.graphLastBuild", {
              at: settings.graph?.last_build?.completed_at || t("settings.graphNotBuilt"),
            })}
            {t("settings.graphHint")}
          </p>
          {graphTrends.length > 0 && (
            <div className="sources">
              <h3>{t("settings.trendHeading")}</h3>
              <ul>
                {graphTrends.map((tr) => (
                  <li key={`${tr.entity_type}-${tr.name}`}>
                    [{tr.entity_type}] {tr.name}（{tr.mentions}）
                  </li>
                ))}
              </ul>
            </div>
          )}

          <h3>{t("settings.knowledgeHeading")}</h3>
          <div className="stats">
            <div>{t("settings.qaTotal", { n: settings.knowledge?.qa_total ?? 0 })}</div>
            <div>
              {t("settings.coverage", {
                n: Math.round((settings.knowledge?.coverage_ratio || 0) * 100),
              })}
            </div>
            <div>{t("settings.unlinkedQa", { n: settings.knowledge?.qa_without_graph_link ?? 0 })}</div>
            <div>{t("settings.verifiedQa", { n: settings.knowledge?.qa_verified ?? 0 })}</div>
          </div>

          <h3>{t("settings.faqHeading")}</h3>
          {(faqs.length > 0 ||
            (Array.isArray(settings.faq_snapshot) && settings.faq_snapshot.length > 0)) && (
            <ul className="import-log">
              {(faqs.length ? faqs : (settings.faq_snapshot as { question: string; answer: string }[])).map(
                (f, faqIdx) => (
                  <li key={`${f.question}-${faqIdx}`}>
                    <strong>Q:</strong> {f.question}
                    <br />
                    <strong>A:</strong> {f.answer}
                  </li>
                ),
              )}
            </ul>
          )}
          {faqs.length === 0 &&
            !(Array.isArray(settings.faq_snapshot) && settings.faq_snapshot.length > 0) && (
              <p className="muted">{t("settings.faqEmpty")}</p>
            )}

          <h3>{t("settings.importHistory")}</h3>
          {imports.length === 0 && <p className="muted">{t("settings.importHistoryEmpty")}</p>}
          <ul className="import-log">
            {imports.map((row) => (
              <li key={row.id}>
                {t("settings.importRow", {
                  id: row.id,
                  filename: row.filename,
                  source: row.source_type,
                  status: row.status,
                  added: row.new_messages,
                  dup: row.duplicate_messages,
                  qa: row.qa_count,
                })}
                {row.completed_at ? ` / ${row.completed_at}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="app-footer">
        <div className="app-footer-row">
          <span>{t("app.copyright", { year: new Date().getFullYear() })}</span>
          <span className="app-footer-sep" aria-hidden="true">
            ·
          </span>
          <span>{t("app.version", { version: APP_VERSION })}</span>
        </div>
        <div className="app-footer-tagline">{t("app.tagline")}</div>
      </footer>
    </div>
  );
}

function ConversationView({
  conversation,
  sources,
  insufficient,
  onCopy,
  onReset,
}: {
  conversation: Conversation;
  sources: Source[];
  insufficient: boolean;
  onCopy: (text: string) => void;
  onReset?: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="thread">
      <div className="thread-head">
        <h2>{conversation.title}</h2>
        {onReset && (
          <button className="link" onClick={onReset}>
            {t("conversation.backToNew")}
          </button>
        )}
      </div>
      {insufficient && <div className="warn">{t("conversation.insufficient")}</div>}
      {(conversation.messages || []).map((m) => (
        <article key={m.id} className={`bubble ${m.role}`}>
          <header>{m.role === "customer" ? t("conversation.customer") : t("conversation.aiReply")}</header>
          <pre>{m.content}</pre>
          {m.role === "ai" && (
            <button onClick={() => onCopy(m.content)}>{t("conversation.copy")}</button>
          )}
        </article>
      ))}
      {sources.length > 0 && (
        <div className="sources">
          <h3>{t("conversation.sources")}</h3>
          <ul>
            {sources.map((s, srcIdx) => (
              <li key={`${s.qa_id}-${srcIdx}`}>
                {t("conversation.pastQa", {
                  id: s.qa_id ?? "",
                  score: Math.round(Number(s.score || 0) * 100),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
