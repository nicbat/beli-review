import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeftRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Coffee,
  Download,
  Flag,
  FolderInput,
  History,
  Home,
  ImageOff,
  ListFilter,
  Pause,
  Play,
  Plus,
  RotateCcw,
  RotateCw,
  Search,
  Settings2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import "./style.css";

type Place = {
  key: string;
  name: string;
  category: string;
  business_id: number;
  position: number;
  score: number | null;
  business: { city?: string; country?: string; cuisines?: string[] };
  notes: { value: string }[];
  photos: {
    id: number;
    image: string;
    thumbnail?: string;
    description: string;
  }[];
  previous_notes?: { value: string }[];
  previous_photos?: {
    id: number;
    image: string;
    thumbnail?: string;
    description: string;
  }[];
  visit_dates: unknown[];
  created_dt: string;
  flags: { no_photos: boolean; no_note: boolean; missing_caption: boolean };
};
type Detail = {
  band: string | null;
  reference: boolean;
  status: string;
  attention: boolean;
  reason: string;
  excluded: boolean;
  missing: boolean;
};
type Comparison = {
  id: string;
  a: string;
  b: string;
  outcome: string;
  active: boolean;
  session: string;
  at: string;
  category: string;
};
type Session = {
  id: string;
  status: string;
  count: number;
  limit: number;
  before: string[];
  proposal: string[];
  pair: string[] | null;
  notice: string;
  answers: string[];
  band_suggestions?: { key: string; band: string; comparison: string }[];
};
type View = {
  revision: number;
  state: {
    account: string | null;
    original: string | null;
    latest: string | null;
    order: Record<string, string[]>;
    places: Record<string, Detail>;
    bands: Record<string, string[]>;
    sessions: Record<string, Session>;
    comparisons: Comparison[];
    moves: { key: string; reason: string; at: string }[];
    issues: {
      id: string;
      kind: string;
      key?: string;
      keys?: string[];
      resolved: boolean;
    }[];
  };
  entries: Record<string, Place>;
  categories: Record<string, string>;
  original: Record<string, string[]>;
  latest: Record<string, string[]>;
  imports: {
    id: string;
    exported_at: string;
    imported_at: string;
    count: number;
  }[];
  history: {
    id: string;
    revision: number;
    created_at: string;
    label: string;
  }[];
  checkpoints: {
    id: string;
    created_at: string;
    name: string;
    order: Record<string, string[]>;
  }[];
  can_undo: boolean;
  can_redo: boolean;
};
type Preview = {
  duplicate: boolean;
  older: boolean;
  count: number;
  added: string[];
  missing: string[];
  changed: string[];
  transfers: string[];
  names: Record<string, string>;
  warnings: string[];
  errors: Record<string, unknown>;
  exported_at: string;
};
type Action = Record<string, unknown>;
const labels: Record<string, string> = {
  RES: "Restaurants",
  COF: "Coffee",
  BAK: "Bakeries",
  DES: "Desserts",
  BAR: "Bars",
};
const date = (s: string) =>
  new Date(s).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
async function api(path: string, body?: unknown) {
  const response = await fetch(
    "/api/" + path,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}

function App() {
  const [v, setV] = useState<View | null>(null),
    [page, setPage] = useState("home"),
    [category, setCategory] = useState("RES"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState("Saved locally"),
    [selected, setSelected] = useState<string | null>(null),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [baseline, setBaseline] = useState("original"),
    [showScores, setShowScores] = useState(false),
    [conflict, setConflict] = useState<Action | null>(null),
    [checkpoint, setCheckpoint] = useState(""),
    [bandEdit, setBandEdit] = useState<string[] | null>(null);
  const [exports, setExports] = useState<{ name: string; size: number }[]>([]),
    [pending, setPending] = useState<{
      payload: unknown;
      report?: unknown;
    } | null>(null),
    [preview, setPreview] = useState<Preview | null>(null),
    [restoreFile, setRestoreFile] = useState<File | null>(null),
    [sessionSize, setSessionSize] = useState(5),
    [moveAnchor, setMoveAnchor] = useState(""),
    [moveSide, setMoveSide] = useState("before"),
    [failedRequest, setFailedRequest] = useState<Action | null>(null);
  const refresh = async () => {
    try {
      const value = await api("state");
      setV(value);
      setError("");
      setSaved("Saved locally");
      setFailedRequest(null);
      if (!value.state.account) setPage("imports");
    } catch (e) {
      setError(String((e as Error).message));
    }
  };
  useEffect(() => {
    void refresh();
    void api("exports")
      .then(setExports)
      .catch(() => {});
  }, []);
  async function act(a: Action): Promise<boolean> {
    if (!v || busy) return false;
    setBusy(true);
    setError("");
    setSaved("Saving…");
    try {
      const request = {
        category,
        revision: v.revision,
        operation_id: crypto.randomUUID(),
        ...a,
      };
      setFailedRequest(request);
      const result = await api("action", request);
      setV(result.view);
      setSaved("Saved locally");
      setConflict(null);
      setFailedRequest(null);
      return true;
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      setSaved("Change not saved");
      if (a.action === "answer" && message.includes("conflicts"))
        setConflict(a);
      if (!(e instanceof TypeError)) setFailedRequest(null);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const s = v?.state;
  const order = s?.order[category] || [];
  const session = s?.sessions[category];
  const entries = v?.entries || {};
  const active = order.filter((k) => !s?.places[k].excluded);
  const newCount = order.filter((k) => s?.places[k].status === "new").length;
  const reviewed = active.filter((k) =>
    ["reviewed", "provisional"].includes(s?.places[k].status || ""),
  ).length;
  const navigate = (p: string) => {
    setPage(p);
    setSelected(null);
    setError("");
  };
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page, category]);
  useEffect(() => {
    setMoveAnchor("");
  }, [selected]);
  useEffect(() => {
    if (!selected && !bandEdit) return;
    const previous = document.activeElement as HTMLElement;
    const dialog = document.querySelector<HTMLElement>("[role=dialog]");
    dialog?.querySelector<HTMLElement>("button,input,select,textarea")?.focus();
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelected(null);
        setBandEdit(null);
      }
      if (e.key === "Tab" && dialog) {
        const nodes = Array.from(
          dialog.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input,select,textarea",
          ),
        );
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, [selected, !!bandEdit]);
  const start = async (target?: string) => {
    if (await act({ action: "start", target, limit: sessionSize })) {
      navigate("review");
    }
  };
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        ["INPUT", "TEXTAREA", "SELECT"].includes(
          (e.target as HTMLElement).tagName,
        ) ||
        busy ||
        page !== "review" ||
        !session?.pair ||
        e.ctrlKey ||
        e.metaKey
      )
        return;
      const outcome = (
        {
          "1": "left",
          "2": "right",
          "3": "equal",
          "4": "unknown",
          "5": "skip",
        } as Record<string, string>
      )[e.key];
      if (outcome) {
        e.preventDefault();
        void act({ action: "answer", outcome });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });
  async function prepare(data: { payload: unknown; report?: unknown }) {
    setBusy(true);
    setError("");
    try {
      setPreview(await api("preview", data));
      setPending(data);
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }
  async function loadLocal(name: string) {
    setError("");
    try {
      await prepare(await api("local-export", { name }));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function readUpload(file?: File) {
    if (!file) return;
    try {
      await prepare({ payload: JSON.parse(await file.text()) });
    } catch {
      setError("Could not read JSON. Select an export.json file.");
    }
  }
  async function restore() {
    if (!restoreFile || !v) return;
    setBusy(true);
    setError("");
    try {
      const buffer = new Uint8Array(await restoreFile.arrayBuffer());
      let binary = "";
      for (let i = 0; i < buffer.length; i += 8192)
        binary += String.fromCharCode(...buffer.subarray(i, i + 8192));
      const result = await api("restore-backup", {
        data: btoa(binary),
        revision: v.revision,
      });
      setV(result.view);
      setRestoreFile(null);
      setSaved("Backup restored");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function changePlace(k: string, patch: Action) {
    return act({ action: "place", key: k, ...patch });
  }
  function badges(k: string) {
    const p = s!.places[k],
      e = entries[k];
    return (
      <div className="badges">
        {p.band && <span>{p.band}</span>}
        {p.status === "new" && <span className="new">New import</span>}
        {p.status === "provisional" && (
          <span>Compared; placement provisional</span>
        )}
        {p.reference && <span>Reference</span>}
        {p.missing && <span className="warn">Absent in latest export</span>}
        {p.excluded && <span className="warn">Need to delete</span>}
        {p.attention && <span className="warn">Needs attention</span>}
        {e.flags.no_note && <span>No note</span>}
        {e.flags.no_photos && <span>No photos</span>}
        {e.flags.missing_caption && <span>Missing caption</span>}
      </div>
    );
  }
  function memory(k: string, side?: number) {
    const e = entries[k],
      p = s!.places[k];
    return (
      <article className="memory" key={k}>
        <div className="memory-top">
          <span className="place-context">
            {e.business.city || "Location unknown"}
          </span>
          {side && <span className="keycap">{side}</span>}
        </div>
        <h2>{e.name}</h2>
        <p className="place-context">
          {(e.business.cuisines || []).join(", ") || labels[e.category]}
        </p>
        <div className="memory-evidence">
          {e.notes.length ? (
            e.notes.map((n, i) => <blockquote key={i}>{n.value}</blockquote>)
          ) : (
            <div className="empty-note">
              <BookOpen size={19} />
              <span>No written note in the export.</span>
            </div>
          )}
          {e.photos.length ? (
            <div className="photos">
              {e.photos.map((photo) => (
                <Photo key={photo.id} photo={photo} />
              ))}
            </div>
          ) : (
            <div className="empty-photo">
              <ImageOff size={25} />
              <span>No photos saved for this place</span>
            </div>
          )}
        </div>
        {(!!e.previous_notes?.length || !!e.previous_photos?.length) && (
          <details>
            <summary>Content retained from earlier exports</summary>
            <p className="small">
              Absent from the latest source. Kept here for reference.
            </p>
            {e.previous_notes?.map((n, i) => (
              <blockquote key={i}>{n.value}</blockquote>
            ))}
            <div className="photos">
              {e.previous_photos?.map((photo) => (
                <Photo key={photo.id} photo={photo} />
              ))}
            </div>
          </details>
        )}
        {e.visit_dates.length > 0 && (
          <p className="small">
            Visit dates:{" "}
            {e.visit_dates
              .map((d) => (typeof d === "string" ? d : JSON.stringify(d)))
              .join(", ")}
          </p>
        )}
        {showScores && (
          <p className="small">
            Imported Beli score: {e.score?.toFixed(2) ?? "Unavailable"} · Source
            position {e.position}
          </p>
        )}
        <label className="field">
          Quality band
          <select
            aria-label={`Quality band for ${e.name}`}
            value={p.band ?? ""}
            disabled={busy}
            onChange={(ev) =>
              void changePlace(k, { band: ev.target.value || null })
            }
          >
            <option value="">Unassigned / unsure</option>
            {s!.bands[category].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </label>
        {badges(k)}
        <div className="card-actions">
          <button
            disabled={busy}
            className={p.reference ? "chosen" : ""}
            onClick={() => void changePlace(k, { reference: !p.reference })}
          >
            <Check size={15} />
            {p.reference ? "Reference place" : "Use as reference"}
          </button>
          <button
            disabled={busy}
            className={p.attention ? "chosen" : ""}
            onClick={() => void changePlace(k, { attention: !p.attention })}
          >
            <Flag size={15} />
            {p.attention ? "Flagged" : "Flag"}
          </button>
          <button
            disabled={busy}
            onClick={() => void changePlace(k, { excluded: !p.excluded })}
          >
            <Trash2 size={15} />
            {p.excluded ? "Restore" : "Need to delete"}
          </button>
        </div>
      </article>
    );
  }
  function changeRows(base: string[], proposed: string[]) {
    const kept = proposed.filter((k) => !s!.places[k]?.excluded),
      before = base.filter((k) => entries[k]);
    const explicit = new Set((s!.moves || []).map((m) => m.key));
    if (session?.status === "active")
      s!.comparisons
        .filter(
          (r) =>
            r.session === session.id &&
            r.active &&
            ["left", "right"].includes(r.outcome),
        )
        .forEach((r) => explicit.add(r.a));
    const moved = kept.filter((k) => before.indexOf(k) !== kept.indexOf(k));
    return (
      <>
        {moved.length === 0 ? (
          <div className="empty">No order changes against this baseline.</div>
        ) : (
          <div className="change-list">
            {moved.map((k) => (
              <div className="change-row" key={k}>
                <div className="rank-change">
                  <span>
                    {before.includes(k) ? before.indexOf(k) + 1 : "New"}
                  </span>
                  <ChevronRight size={16} />
                  <strong>{kept.indexOf(k) + 1}</strong>
                </div>
                <div>
                  <button
                    className="text-button"
                    onClick={() => setSelected(k)}
                  >
                    {entries[k].name}
                  </button>
                  <p className="small">
                    {explicit.has(k) ? "Explicitly moved" : "Position shifted"}{" "}
                    · Was{" "}
                    {before.indexOf(k) > 0
                      ? `below ${entries[before[before.indexOf(k) - 1]]?.name}`
                      : before.includes(k)
                        ? "top of list"
                        : "not in this baseline"}
                    ; now{" "}
                    {kept.indexOf(k) > 0
                      ? `below ${entries[kept[kept.indexOf(k) - 1]]?.name}`
                      : "top of list"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="small">
          Positions describe your working order. Imported Beli scores are
          unchanged.
        </p>
      </>
    );
  }
  if (!v)
    return (
      <div className="loading">
        <Coffee size={36} />
        <h1>Opening your workshop…</h1>
        {error && <p role="alert">{error}</p>}
      </div>
    );
  const filters: Record<string, (k: string) => boolean> = {
    all: () => true,
    new: (k) => s!.places[k].status === "new",
    unreviewed: (k) => s!.places[k].status === "unreviewed",
    uncertain: (k) => s!.places[k].status === "uncertain",
    missing: (k) =>
      entries[k].flags.no_note ||
      entries[k].flags.no_photos ||
      entries[k].flags.missing_caption,
    no_note: (k) => entries[k].flags.no_note,
    no_photos: (k) => entries[k].flags.no_photos,
    missing_caption: (k) => entries[k].flags.missing_caption,
    neither: (k) => entries[k].flags.no_note && entries[k].flags.no_photos,
    attention: (k) => s!.places[k].attention,
    delete: (k) => s!.places[k].excluded,
  };
  const filtered = order.filter(
    (k) =>
      (filters[filter] || filters.all)(k) &&
      `${entries[k]?.name} ${entries[k]?.business.city || ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const nav = [
    ["home", "Overview", Home],
    ["review", "Guided review", ArrowLeftRight],
    ["library", "Your places", BookOpen],
    ["cleanup", "Cleanup", ClipboardList],
    ["changes", "Before & after", History],
    ["imports", "Imports & backups", FolderInput],
  ] as const;
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("home");
          }}
        >
          <span className="brand-mark">
            <ArrowLeftRight size={22} />
          </span>
          <span>
            Beli Review<small>A little perspective.</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          {nav.map(([id, label, Icon]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <Icon size={19} />
              {label}
              {id === "cleanup" && (
                <span className="nav-count">
                  {
                    order.filter(
                      (k) => s!.places[k].excluded || s!.places[k].attention,
                    ).length
                  }
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="local-dot" />
          On this computer
          <p>
            Your work saves as you go.
            <br />
            Close it whenever you need.
          </p>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <label className="category-label">
            Your list
            <select
              aria-label="Category"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setSelected(null);
                setBandEdit(null);
              }}
            >
              {Object.entries({ ...labels, ...v.categories }).map(
                ([c, name]) => (
                  <option key={c} value={c}>
                    {name}
                    {s!.order[c] ? ` (${s!.order[c].length})` : ""}
                  </option>
                ),
              )}
            </select>
          </label>
          <div className="save-tools">
            <span
              role="status"
              className={saved === "Change not saved" ? "save-error" : "saved"}
            >
              {busy ? <span className="spinner" /> : <Check size={15} />}{" "}
              {saved}
            </span>
            <button
              className="icon-button"
              title="Undo last action"
              aria-label="Undo last action"
              disabled={busy || !v.can_undo}
              onClick={() => void act({ action: "undo" })}
            >
              <RotateCcw size={18} />
            </button>
            <button
              className="icon-button"
              title="Redo last action"
              aria-label="Redo last action"
              disabled={busy || !v.can_redo}
              onClick={() => void act({ action: "redo" })}
            >
              <RotateCw size={18} />
            </button>
          </div>
        </header>
        <main>
          {error && (
            <div className="error" role="alert">
              <div>{error}</div>
              <button onClick={() => void refresh()}>Reload saved state</button>
              {failedRequest && (
                <button disabled={busy} onClick={() => void act(failedRequest)}>
                  Retry unsaved change
                </button>
              )}
              {conflict && (
                <button
                  disabled={busy}
                  onClick={() => void act({ ...conflict, supersede: true })}
                >
                  Replace conflicting preferences
                </button>
              )}
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => {
                  setError("");
                  setConflict(null);
                }}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {page === "home" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="context">Your ranking workshop</p>
                  <h1>Make room for a second thought.</h1>
                  <p>Small comparisons. A list that feels more like you.</p>
                </div>
                <Coffee className="heading-drawing" size={74} strokeWidth={1} />
              </div>
              {!s!.account ? (
                <div className="hero">
                  <h2>Bring your Beli list along.</h2>
                  <p>
                    Start with an export. Your original ranking stays preserved.
                  </p>
                  <button
                    className="primary"
                    onClick={() => navigate("imports")}
                  >
                    Import your places <Upload size={17} />
                  </button>
                </div>
              ) : (
                <>
                  <section className="hero">
                    <div>
                      <span className="pill">
                        {labels[category] || category}
                      </span>
                      <h2>
                        {session?.status === "active"
                          ? "Pick up where you left off."
                          : "A few places. A clearer picture."}
                      </h2>
                      <p>
                        {session?.status === "active"
                          ? `${session.count} of ${session.limit} comparisons saved. Your session is ready to continue.`
                          : "Choose broad quality bands, then compare places you remember. There’s no need to start over."}
                      </p>
                      <div className="hero-actions">
                        <button
                          className="primary"
                          disabled={busy || active.length < 2}
                          onClick={() =>
                            session?.status === "active"
                              ? navigate("review")
                              : void start()
                          }
                        >
                          <Play size={17} />
                          {session?.status === "active"
                            ? "Resume session"
                            : "Start a short session"}
                        </button>
                        <select
                          aria-label="Comparisons per session"
                          value={sessionSize}
                          onChange={(e) =>
                            setSessionSize(Number(e.target.value))
                          }
                        >
                          {[3, 5, 10].map((n) => (
                            <option key={n} value={n}>
                              {n} comparisons
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div
                      className="progress-ring"
                      style={
                        {
                          "--progress": `${active.length ? (reviewed / active.length) * 100 : 0}%`,
                        } as React.CSSProperties
                      }
                    >
                      <div>
                        <strong>{reviewed}</strong>
                        <span>of {active.length} reviewed</span>
                      </div>
                    </div>
                  </section>
                  <div className="overview-grid">
                    <section className="panel">
                      <div className="section-title">
                        <h2>Your quality bands</h2>
                        <button
                          className="text-button"
                          onClick={() =>
                            setBandEdit(s!.bands[category]?.slice() || [])
                          }
                        >
                          <Settings2 size={16} />
                          Edit bands
                        </button>
                      </div>
                      <p className="small">
                        Assigned bands group places from best to worst.
                        Unassigned places keep their relative order below them.
                      </p>
                      {(s!.bands[category] || []).map((band, i) => (
                        <div className="band-row" key={band}>
                          <span className={`band-dot band-${i}`} />
                          <span>{band}</span>
                          <strong>
                            {
                              active.filter((k) => s!.places[k].band === band)
                                .length
                            }
                          </strong>
                        </div>
                      ))}
                      <div className="band-row">
                        <CircleHelp size={15} />
                        <span>Unassigned / unsure</span>
                        <strong>
                          {active.filter((k) => !s!.places[k].band).length}
                        </strong>
                      </div>
                      <button
                        className="secondary full"
                        onClick={() => {
                          setFilter("all");
                          navigate("library");
                        }}
                      >
                        Browse and assign bands
                      </button>
                    </section>
                    <section className="panel queue-panel">
                      <h2>A little housekeeping</h2>
                      <button
                        className="queue-link"
                        onClick={() => {
                          setFilter("new");
                          navigate("library");
                        }}
                      >
                        <Plus size={21} />
                        <span>
                          <strong>New since last import</strong>
                          <small>Find a home for new places</small>
                        </span>
                        <b>{newCount}</b>
                      </button>
                      <button
                        className="queue-link"
                        onClick={() => {
                          setFilter("missing");
                          navigate("cleanup");
                        }}
                      >
                        <ImageOff size={21} />
                        <span>
                          <strong>Missing information</strong>
                          <small>Notes, photos, and captions</small>
                        </span>
                        <b>{order.filter(filters.missing).length}</b>
                      </button>
                      <button
                        className="queue-link"
                        onClick={() => {
                          setFilter("delete");
                          navigate("cleanup");
                        }}
                      >
                        <Trash2 size={21} />
                        <span>
                          <strong>Need to delete</strong>
                          <small>A reversible holding box</small>
                        </span>
                        <b>{order.filter(filters.delete).length}</b>
                      </button>
                      <p className="small">
                        Changes here stay local. Nothing is sent to Beli.
                      </p>
                    </section>
                  </div>
                </>
              )}
            </>
          )}
          {page === "review" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="context">Guided review</p>
                  <h1>Which would you choose again?</h1>
                  <p>
                    Think about your overall experience. It’s fine not to
                    remember.
                  </p>
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={showScores}
                    onChange={(e) => setShowScores(e.target.checked)}
                  />
                  Show source scores
                </label>
              </div>
              {session?.status === "active" ? (
                <>
                  <div className="session-strip">
                    <span>
                      {session.count} / {session.limit} comparisons saved
                    </span>
                    <div className="session-progress">
                      <i
                        style={{
                          width: `${(session.count / session.limit) * 100}%`,
                        }}
                      />
                    </div>
                    <button onClick={() => navigate("home")}>
                      <Pause size={15} />
                      Pause
                    </button>
                    <button onClick={() => setPage("changes")}>
                      Review session
                    </button>
                  </div>
                  {session.notice && <p className="notice">{session.notice}</p>}
                  {(session.band_suggestions || [])
                    .filter((item) => s!.places[item.key].band !== item.band)
                    .map((item) => (
                      <div className="notice" key={item.comparison}>
                        This comparison crosses your bands. Consider moving{" "}
                        {entries[item.key]?.name} to “{item.band}”.{" "}
                        <button
                          disabled={busy}
                          onClick={() =>
                            void changePlace(item.key, { band: item.band })
                          }
                        >
                          Use this band
                        </button>
                      </div>
                    ))}
                  {session.pair ? (
                    <>
                      <div className="comparison-grid">
                        {memory(session.pair[0], 1)}
                        <span className="versus">or</span>
                        {memory(session.pair[1], 2)}
                      </div>
                      <div className="answer-bar">
                        <div className="prefer-buttons">
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() =>
                              void act({ action: "answer", outcome: "left" })
                            }
                          >
                            <span className="keycap">1</span>Prefer{" "}
                            {entries[session.pair[0]].name}
                          </button>
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() =>
                              void act({ action: "answer", outcome: "right" })
                            }
                          >
                            <span className="keycap">2</span>Prefer{" "}
                            {entries[session.pair[1]].name}
                          </button>
                        </div>
                        <div className="uncertain-buttons">
                          <button
                            disabled={busy}
                            onClick={() =>
                              void act({ action: "answer", outcome: "equal" })
                            }
                          >
                            3 · About equal
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void act({ action: "answer", outcome: "unknown" })
                            }
                          >
                            4 · Don’t remember
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void act({ action: "answer", outcome: "skip" })
                            }
                          >
                            5 · Skip for now
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <section className="panel">
                      <h2>Your session is ready to review.</h2>
                      <p>
                        {session.count} answers saved. Review the proposed
                        ordering before accepting it.
                      </p>
                      {changeRows(session.before, session.proposal)}
                      <div className="actions">
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => void act({ action: "accept" })}
                        >
                          Accept session
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => void act({ action: "discard" })}
                        >
                          Discard proposal
                        </button>
                      </div>
                    </section>
                  )}
                </>
              ) : (
                <section className="panel empty">
                  <ArrowLeftRight size={38} />
                  <h2>
                    {session
                      ? "Session finished."
                      : "Start with a few familiar places."}
                  </h2>
                  <p>
                    Each choice is saved. About equal and unsure are always
                    available.
                  </p>
                  <button
                    className="primary"
                    disabled={busy || active.length < 2}
                    onClick={() => void start()}
                  >
                    Start {sessionSize} comparisons
                  </button>
                </section>
              )}
            </>
          )}
          {(page === "library" || page === "cleanup") && (
            <>
              <div className="page-heading">
                <div>
                  <p className="context">{labels[category]}</p>
                  <h1>
                    {page === "cleanup"
                      ? "Leave yourself a little less to do."
                      : "Every place has a story."}
                  </h1>
                  <p>
                    {page === "cleanup"
                      ? "Flag missing memories or set places aside for deletion."
                      : "Browse your notes, choose quality bands, and revisit a placement."}
                  </p>
                </div>
              </div>
              <div className="list-toolbar">
                <label className="search">
                  <Search size={18} />
                  <input
                    aria-label="Search places"
                    placeholder="Search names or cities"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <label className="filter">
                  <ListFilter size={18} />
                  <select
                    aria-label="Filter places"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="all">All places</option>
                    <option value="new">New since last import</option>
                    <option value="unreviewed">Unreviewed</option>
                    <option value="uncertain">Don’t remember</option>
                    <option value="missing">Any missing information</option>
                    <option value="no_note">No written note</option>
                    <option value="no_photos">No photos</option>
                    <option value="missing_caption">
                      Photo missing caption
                    </option>
                    <option value="neither">Neither note nor photos</option>
                    <option value="attention">Needs attention</option>
                    <option value="delete">Need to delete</option>
                  </select>
                </label>
                <span className="small">{filtered.length} places</span>
              </div>
              <div className="place-list">
                {filtered.length ? (
                  filtered.map((k) => (
                    <div className="place-row" key={k}>
                      <span className="position">
                        {s!.places[k].excluded ? "—" : active.indexOf(k) + 1}
                      </span>
                      <button
                        className="place-name"
                        onClick={() => setSelected(k)}
                      >
                        <strong>{entries[k].name}</strong>
                        <small>
                          {entries[k].business.city || "Location unknown"}
                          {s!.places[k].status === "reviewed"
                            ? " · Reviewed"
                            : ""}
                        </small>
                        {badges(k)}
                      </button>
                      <select
                        aria-label={`Band for ${entries[k].name}`}
                        disabled={busy}
                        value={s!.places[k].band || ""}
                        onChange={(e) =>
                          void changePlace(k, { band: e.target.value || null })
                        }
                      >
                        <option value="">Unassigned / unsure</option>
                        {s!.bands[category].map((b) => (
                          <option key={b}>{b}</option>
                        ))}
                      </select>
                      <button
                        className="icon-button"
                        aria-label={`Flag ${entries[k].name}`}
                        disabled={busy}
                        onClick={() =>
                          void changePlace(k, {
                            attention: !s!.places[k].attention,
                          })
                        }
                      >
                        <Flag
                          size={18}
                          fill={
                            s!.places[k].attention ? "currentColor" : "none"
                          }
                        />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={`${s!.places[k].excluded ? "Restore" : "Set aside"} ${entries[k].name}`}
                        disabled={busy}
                        onClick={() =>
                          void changePlace(k, {
                            excluded: !s!.places[k].excluded,
                          })
                        }
                      >
                        {s!.places[k].excluded ? (
                          <RotateCcw size={18} />
                        ) : (
                          <Trash2 size={18} />
                        )}
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    <Check size={30} />
                    <h2>No places in this view.</h2>
                    <p>Try another filter or search.</p>
                  </div>
                )}
              </div>
            </>
          )}
          {page === "changes" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="context">Before & after</p>
                  <h1>See what feels different.</h1>
                  <p>
                    Compare your working list with where you started, or with
                    the latest Beli export.
                  </p>
                </div>
              </div>
              <div className="actions">
                <label className="field">
                  Compare against
                  <select
                    aria-label="Comparison baseline"
                    value={baseline}
                    onChange={(e) => setBaseline(e.target.value)}
                  >
                    <option value="original">Original export</option>
                    <option value="latest">Latest Beli export</option>
                    {v.checkpoints.map((cp) => (
                      <option key={cp.id} value={cp.id}>
                        {cp.name}
                      </option>
                    ))}
                    {session && (
                      <option value="session">
                        Start of current / last session
                      </option>
                    )}
                  </select>
                </label>
                {session?.status === "active" && (
                  <>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => void act({ action: "accept" })}
                    >
                      Accept session
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => void act({ action: "discard" })}
                    >
                      Discard proposal
                    </button>
                    <button onClick={() => navigate("review")}>
                      Continue comparing
                    </button>
                  </>
                )}
              </div>
              {session?.status === "active" && (
                <p className="notice">
                  Showing the saved session proposal. Accept it to update your
                  working order.
                </p>
              )}
              {changeRows(
                baseline === "session"
                  ? session?.before || []
                  : baseline === "latest"
                    ? v.latest[category] || []
                    : baseline === "original"
                      ? v.original[category] || []
                      : v.checkpoints.find((cp) => cp.id === baseline)?.order[
                          category
                        ] || [],
                session?.status === "active" ? session.proposal : order,
              )}
              <details className="panel">
                <summary>
                  Need to delete ({order.filter(filters.delete).length})
                </summary>
                {order.filter(filters.delete).map((k) => (
                  <p key={k}>
                    {entries[k].name}{" "}
                    <button
                      onClick={() => void changePlace(k, { excluded: false })}
                    >
                      Restore
                    </button>
                  </p>
                ))}
              </details>
              <details className="panel">
                <summary>
                  Comparison evidence (
                  {s!.comparisons.filter((r) => r.category === category).length}
                  )
                </summary>
                {s!.comparisons
                  .filter((r) => r.category === category)
                  .slice()
                  .reverse()
                  .map((r) => (
                    <p className="evidence-line" key={r.id}>
                      {entries[r.a]?.name} / {entries[r.b]?.name}:{" "}
                      <strong>
                        {
                          (
                            {
                              left: "preferred first",
                              right: "preferred second",
                              equal: "about equal",
                              unknown: "don’t remember",
                              skip: "skipped",
                            } as Record<string, string>
                          )[r.outcome]
                        }
                      </strong>
                      {!r.active ? " (superseded or discarded)" : ""}{" "}
                      <button
                        disabled={busy || session?.status === "active"}
                        onClick={async () => {
                          if (await act({ action: "revisit", id: r.id }))
                            navigate("review");
                        }}
                      >
                        Revisit
                      </button>
                    </p>
                  ))}
              </details>
            </>
          )}
          {page === "imports" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="context">Imports & backups</p>
                  <h1>Keep the memories. Keep your progress.</h1>
                  <p>
                    Bring in a fresh Beli export whenever you like. Your local
                    decisions stay yours.
                  </p>
                </div>
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <h2>Import a Beli export</h2>
                  <p className="small">
                    Select export.json from the existing exporter. Files are
                    processed on this computer.
                  </p>
                  <label className="upload-button">
                    <Upload size={18} />
                    Choose export.json
                    <input
                      type="file"
                      accept=".json"
                      disabled={busy}
                      onChange={(e) => void readUpload(e.target.files?.[0])}
                    />
                  </label>
                  {exports.length > 0 && (
                    <>
                      <h3>Available on this computer</h3>
                      {exports.map((f) => (
                        <button
                          className="local-export"
                          disabled={busy}
                          key={f.name}
                          onClick={() => void loadLocal(f.name)}
                        >
                          <FolderInput size={18} />
                          <span>
                            {f.name}
                            <small>
                              {(f.size / 1024 / 1024).toFixed(1)} MB
                            </small>
                          </span>
                          <ChevronRight size={18} />
                        </button>
                      ))}
                    </>
                  )}
                </section>
                <section className="panel">
                  <h2>A copy you can keep</h2>
                  <p>
                    Back up your rankings, comparisons, source snapshots, and
                    saved sessions.
                  </p>
                  <a
                    className="button secondary"
                    href="/api/backup"
                    download={`beli-review-${new Date().toISOString().slice(0, 10)}.sqlite3`}
                  >
                    <Download size={18} />
                    Download workspace backup
                  </a>
                  <p className="small">
                    Includes photo links and captions. Image files are not
                    included.
                  </p>
                  <label className="upload-button subtle">
                    <History size={18} />
                    Restore a workspace backup
                    <input
                      type="file"
                      accept=".sqlite3,.db"
                      disabled={busy}
                      onChange={(e) =>
                        setRestoreFile(e.target.files?.[0] || null)
                      }
                    />
                  </label>
                  {restoreFile && (
                    <div className="notice">
                      <p>
                        Restore {restoreFile.name}? This replaces your working
                        workspace. A recovery backup of the current state will
                        be saved locally first.
                      </p>
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => void restore()}
                      >
                        Restore this backup
                      </button>
                      <button onClick={() => setRestoreFile(null)}>
                        Cancel
                      </button>
                    </div>
                  )}
                </section>
              </div>
              {preview && (
                <section className="panel import-preview">
                  <h2>
                    {preview.duplicate
                      ? "Already imported"
                      : preview.older
                        ? "Archive an older export"
                        : "Review this import"}
                  </h2>
                  <p>
                    {preview.count} places · Exported{" "}
                    {date(preview.exported_at)}
                  </p>
                  <div className="import-counts">
                    <span>
                      <b>{preview.added.length}</b>new memberships
                    </span>
                    <span>
                      <b>{preview.changed.length}</b>changed source records
                    </span>
                    <span>
                      <b>{preview.missing.length}</b>absent memberships
                    </span>
                    <span>
                      <b>{preview.transfers.length}</b>possible category
                      transfers
                    </span>
                  </div>
                  {preview.warnings.length > 0 && (
                    <p className="notice">{preview.warnings.join(" ")}</p>
                  )}
                  {Object.keys(preview.errors).length > 0 && (
                    <p className="notice">
                      The export reports request errors. Missing places will
                      stay in your workspace for review.
                    </p>
                  )}
                  <p className="small">
                    {preview.older
                      ? "This snapshot will be archived without replacing the latest source or your working list."
                      : "Existing local order, flags, and comparisons are preserved. New items go to the review inbox; source absences need review."}
                  </p>
                  {[
                    ["added", "New places"],
                    ["missing", "Absent places"],
                    ["changed", "Changed records"],
                  ].map(([field, title]) => (
                    <details key={field}>
                      <summary>{title}</summary>
                      <ul>
                        {preview[field as "added" | "missing" | "changed"].map(
                          (k) => (
                            <li key={k}>{preview.names[k]}</li>
                          ),
                        )}
                      </ul>
                    </details>
                  ))}
                  <div className="actions">
                    <button
                      className="primary"
                      disabled={busy || preview.duplicate}
                      onClick={async () => {
                        if (await act({ action: "import", ...pending })) {
                          setPreview(null);
                          setPending(null);
                        }
                      }}
                    >
                      {preview.older
                        ? "Archive snapshot"
                        : "Import and preserve my work"}
                    </button>
                    <button
                      onClick={() => {
                        setPreview(null);
                        setPending(null);
                      }}
                    >
                      Dismiss
                    </button>
                  </div>
                </section>
              )}
              {s!.issues.some((i) => !i.resolved) && (
                <section className="panel">
                  <h2>Import differences to review</h2>
                  {s!.issues
                    .filter((i) => !i.resolved)
                    .map((i) => (
                      <div className="issue-row" key={i.id}>
                        <span>
                          {i.kind === "missing"
                            ? `${entries[i.key!]?.name}: absent from latest source`
                            : i.kind === "category"
                              ? `${entries[i.key!]?.name}: possible category transfer`
                              : `${i.keys?.length} source records changed; working order preserved.`}
                        </span>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act({ action: "resolve", id: i.id })
                          }
                        >
                          Acknowledge
                        </button>
                      </div>
                    ))}
                </section>
              )}
              <section className="panel">
                <h2>Checkpoints</h2>
                <div className="actions">
                  <input
                    aria-label="Checkpoint name"
                    placeholder="e.g. Before the coffee review"
                    value={checkpoint}
                    onChange={(e) => setCheckpoint(e.target.value)}
                  />
                  <button
                    disabled={busy}
                    onClick={async () => {
                      if (await act({ action: "checkpoint", name: checkpoint }))
                        setCheckpoint("");
                    }}
                  >
                    <Plus size={16} />
                    Save checkpoint
                  </button>
                </div>
                {v.checkpoints.map((cp) => (
                  <div className="issue-row" key={cp.id}>
                    <span>
                      {cp.name}
                      <small>{date(cp.created_at)}</small>
                    </span>
                    <button
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Restore “${cp.name}”? The current state will be checkpointed first.`,
                          )
                        )
                          void act({ action: "restore", id: cp.id });
                      }}
                    >
                      Restore
                    </button>
                  </div>
                ))}
              </section>
              <details className="panel">
                <summary>Import snapshots ({v.imports.length})</summary>
                {v.imports.map((i) => (
                  <p key={i.id}>
                    {date(i.exported_at)} · {i.count} places{" "}
                    {i.id === s!.latest ? "· Latest source" : ""}
                    {i.id === s!.original ? " · Original" : ""}
                  </p>
                ))}
              </details>
              <details className="panel">
                <summary>Recent saved actions</summary>
                {v.history.map((h) => (
                  <div className="issue-row" key={h.id}>
                    <span>{h.label}</span>
                    <small>{new Date(h.created_at).toLocaleString()}</small>
                  </div>
                ))}
              </details>
            </>
          )}
        </main>
        <footer>
          Your original export stays preserved. Review decisions are local to
          this computer.
        </footer>
      </div>
      {selected && entries[selected] && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Place details"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close icon-button"
              aria-label="Close place details"
              onClick={() => setSelected(null)}
            >
              <X />
            </button>
            {memory(selected)}
            <div className="drawer-extra">
              <label className="field">
                Attention / deletion reason
                <Reason
                  key={selected}
                  value={s!.places[selected].reason}
                  save={(value) =>
                    void changePlace(selected, { reason: value })
                  }
                />
              </label>
              <div className="actions">
                <button
                  className="primary"
                  disabled={
                    busy ||
                    session?.status === "active" ||
                    s!.places[selected].excluded
                  }
                  onClick={() => void start(selected)}
                >
                  Review this place
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    void changePlace(selected, {
                      status:
                        s!.places[selected].status === "reviewed"
                          ? "unreviewed"
                          : "reviewed",
                    })
                  }
                >
                  {s!.places[selected].status === "reviewed"
                    ? "Mark unreviewed"
                    : "Looks right"}
                </button>
              </div>
              <details>
                <summary>Move relative to another place</summary>
                <p className="small">
                  A manual move replaces older preferences that contradict this
                  placement.
                </p>
                <label className="field">
                  Position
                  <select
                    aria-label="Move position"
                    value={moveSide}
                    onChange={(e) => setMoveSide(e.target.value)}
                  >
                    <option value="before">Above</option>
                    <option value="after">Below</option>
                  </select>
                </label>
                <label className="field">
                  Place
                  <select
                    aria-label="Move relative to place"
                    value={moveAnchor}
                    onChange={(e) => setMoveAnchor(e.target.value)}
                  >
                    <option value="">Choose a place</option>
                    {order
                      .filter((k) => k !== selected && !s!.places[k].excluded)
                      .map((k) => (
                        <option key={k} value={k}>
                          {entries[k].name}
                        </option>
                      ))}
                  </select>
                </label>
                <button
                  disabled={busy || !moveAnchor || session?.status === "active"}
                  onClick={() =>
                    void act({
                      action: "move",
                      key: selected,
                      anchor: moveAnchor,
                      side: moveSide,
                    })
                  }
                >
                  Move place
                </button>
                {session?.status === "active" && (
                  <p className="small">
                    Finish the current session before making a manual move.
                  </p>
                )}
              </details>
              <p className="small">
                Using a reference means you trust this place as a comparison
                anchor. It does not verify its neighbors.
              </p>
            </div>
          </section>
        </div>
      )}
      {bandEdit && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Edit quality bands"
          >
            <h2>Your quality bands</h2>
            <p>Best first. Renaming preserves assignments by position.</p>
            {bandEdit.map((b, i) => (
              <label className="field" key={i}>
                Band {i + 1}
                <input
                  value={b}
                  onChange={(e) =>
                    setBandEdit(
                      bandEdit.map((x, j) => (j === i ? e.target.value : x)),
                    )
                  }
                />
              </label>
            ))}
            <div className="actions">
              <button
                onClick={() => setBandEdit([...bandEdit, ""])}
                disabled={bandEdit.length >= 10}
              >
                Add band
              </button>
              <button
                onClick={() => setBandEdit(bandEdit.slice(0, -1))}
                disabled={bandEdit.length <= 1}
              >
                Remove last
              </button>
            </div>
            <div className="actions">
              <button
                className="primary"
                disabled={busy}
                onClick={async () => {
                  if (await act({ action: "bands", bands: bandEdit }))
                    setBandEdit(null);
                }}
              >
                Save bands
              </button>
              <button onClick={() => setBandEdit(null)}>Cancel</button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function Photo({
  photo,
}: {
  photo: { image: string; thumbnail?: string; description: string };
}) {
  const [failed, setFailed] = useState(false);
  return (
    <figure>
      {failed ? (
        <div className="photo-failed">
          <ImageOff size={20} />
          Image unavailable
        </div>
      ) : (
        <img
          src={photo.thumbnail || photo.image}
          alt={photo.description || "Food photo"}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      )}
      <figcaption>{photo.description || "No caption"}</figcaption>
    </figure>
  );
}
function Reason({
  value,
  save,
}: {
  value: string;
  save: (value: string) => void;
}) {
  const [text, setText] = useState(value);
  return (
    <textarea
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        if (text !== value) save(text);
      }}
      placeholder="Optional note for later"
    />
  );
}
createRoot(document.getElementById("root")!).render(<App />);
