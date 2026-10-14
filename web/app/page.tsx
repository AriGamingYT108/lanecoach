"use client";
import {FormEvent, useEffect, useRef, useState} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Role = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";
type Profile = {role: Role; champion: string; opponent: string; rank: string; goal: string; patch: string | null};
type Source = {id: string; title: string; patch: string | null; source_kind: string; source_url: string | null};
type Message = {role: "user" | "assistant"; content: string; sources?: Source[]};
type Champion = {id: string; name: string; title: string};
type Health = {public_demo?: boolean; database_ready: boolean; ai_configured: boolean; riot_configured: boolean; catalog_version: string | null; matches: number; documents: number; participants: number; engine: string};
type Measure = {sample_size: number; wins: number; win_rate: number | null};
type Analytics = {overall: Measure; runes: (Measure & {keystone: number})[]; opponents: (Measure & {opponent: string})[]; note: string};
const roles: {id: Role; label: string; symbol: string; description: string}[] = [
  {id: "TOP", label: "Top", symbol: "↖", description: "Trading, waves & side lanes"},
  {id: "JUNGLE", label: "Jungle", symbol: "♧", description: "Routing, pressure & objectives"},
  {id: "MIDDLE", label: "Mid", symbol: "◇", description: "Pressure, tempo & roams"},
  {id: "BOTTOM", label: "Bot", symbol: "↘", description: "Farm, spacing & teamfights"},
  {id: "UTILITY", label: "Support", symbol: "✧", description: "Vision, engages & map impact"}
];
const defaultProfile: Profile = {role: "TOP", champion: "", opponent: "", rank: "Learning", goal: "Make better decisions", patch: null};
let visitorPromise: Promise<string> | null = null;
function initializeVisitor(): Promise<string> {
  if (!visitorPromise) visitorPromise = fetch('/api/visitor', {cache: 'no-store'}).then(async response => {
    if (!response.ok) throw new Error('Could not initialize your coaching session. Reload and try again.');
    return (await response.json()).csrf_token as string;
  }).catch(error => {visitorPromise = null; throw error;});
  return visitorPromise;
}
async function api<T>(path: string, body?: unknown): Promise<T> {
  const csrf = body ? await initializeVisitor() : '';
  const response = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json", "X-LaneCoach-Client": "browser", 'X-LaneCoach-CSRF': csrf}, body: JSON.stringify(body)} : {cache: "no-store"});
  let data;
  try {data = await response.json();} catch {throw new Error("The API is unavailable. Start the FastAPI service and PostgreSQL.");}
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check your request and try again.");
  return data as T;
}

export default function Home() {
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [champions, setChampions] = useState<Champion[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [section, setSection] = useState<"coach" | "evidence" | "about">("coach");
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [restoring, setRestoring] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);
  const role = roles.find(r => r.id === profile.role)!;
  const championName = (id: string) => champions.find(c => c.id.toLowerCase() === id.toLowerCase() || c.name.toLowerCase() === id.toLowerCase())?.name || id;

  useEffect(() => {
    async function boot() {
      try {
        const [h, c] = await Promise.all([api<Health>("/api/health"), api<{champions: Champion[]}>("/api/champions")]);
        setHealth(h); setChampions(c.champions);
        const saved = localStorage.getItem("lanecoach-v2-session");
        if (saved && h.database_ready) {
          try {const conversation = await api<{id: string; profile: Profile; messages: Message[]}>(`/api/sessions/${encodeURIComponent(saved)}`); setProfile(conversation.profile); setMessages(conversation.messages); setSessionId(conversation.id);} catch {localStorage.removeItem("lanecoach-v2-session");}
        }
      } catch (e) {setError((e as Error).message);} finally {setRestoring(false);}
    }
    void boot();
  }, []);
  useEffect(() => {if (messages.length) bottom.current?.scrollIntoView({behavior: "smooth", block: "end"});}, [messages, busy]);

  function reset() {setSessionId(null); setMessages([]); setAnalytics(null); setError(""); localStorage.removeItem("lanecoach-v2-session");}
  function update<K extends keyof Profile>(key: K, value: Profile[K]) {reset(); setProfile(p => ({...p, [key]: value}));}
  async function send(text: string) {
    if (busy || !text.trim()) return;
    setError(""); setSection("coach"); setBusy(true);
    const previous = messages;
    setMessages([...messages, {role: "user", content: text}]); setQuestion("");
    try {
      const reply = await api<{session_id: string; text: string; sources: Source[]; analytics: Analytics | null}>("/api/coach", {profile, question: text, session_id: sessionId});
      setMessages([...previous, {role: "user", content: text}, {role: "assistant", content: reply.text, sources: reply.sources}]);
      setSessionId(reply.session_id); setAnalytics(reply.analytics); localStorage.setItem("lanecoach-v2-session", reply.session_id);
    } catch (e) {setMessages(previous); setQuestion(text); setError((e as Error).message);} finally {setBusy(false);}
  }
  function submit(event: FormEvent) {event.preventDefault(); void send(question);}
  async function evidence() {
    setSection("evidence"); setError("");
    if (!profile.champion) {setAnalytics(null); return;}
    try {const params = new URLSearchParams({champion: profile.champion, role: profile.role}); if (profile.opponent) params.set("opponent", profile.opponent); if (profile.patch) params.set("patch", profile.patch); setAnalytics(await api<Analytics>(`/api/analytics?${params}`));} catch(e) {setError((e as Error).message);}
  }
  const suggestions = profile.role === "JUNGLE" ? ["How should I decide my first clear direction?", "When should I farm instead of forcing a gank?", "Help me prepare for the next objective."] : profile.role === "UTILITY" ? ["When is a support roam worth it?", "How do I set up vision safely?", "How can I coordinate better trades?"] : ["How do I play this matchup from behind?", "When should I trade instead of farming?", "How do I decide when to recall?"];

  return <div className="app-shell">
    <aside className="sidebar"><a href="/" className="brand"><span className="brand-mark">L</span><span>Lane<span className="lime">Coach</span><small>YOUR LEAGUE COACH</small></span></a>
      <div className="nav"><button className={section === "coach" ? "selected" : ""} onClick={() => setSection("coach")}>✦ Your coach</button><button className={section === "evidence" ? "selected" : ""} onClick={() => void evidence()}>◈ Supporting evidence</button><button className={section === "about" ? "selected" : ""} onClick={() => setSection("about")}>ⓘ How it works</button></div>
      <div className="side-context"><p className="eyebrow">YOUR FOCUS</p><strong>{role.label}</strong><p>{role.description}</p><button className="new-chat" disabled={busy} onClick={reset}>＋ New conversation</button></div>
      <div className="side-footer"><span className="dot"/> Coach-first. Every role.<p>You bring the question.<br/>We build a practice plan.</p></div>
    </aside>
    <main>
      <header><span>WORKSPACE <b>/</b> {section === "coach" ? "Your coach" : section === "evidence" ? "Supporting evidence" : "How it works"}</span><span className="tag">ALL FIVE ROLES</span></header>
      {error && <div className="alert" role="alert">{error}</div>}
      {health && !health.database_ready && <div className="alert" role="status">PostgreSQL isn’t ready. Start the database and restart FastAPI. Your coach saves conversations and retrieves knowledge from it.</div>}
      {section === "coach" && <>
        <div className="heading"><p className="eyebrow">LESS GUESSING. BETTER DECISIONS.</p><h1>Your game. Your questions.<br/><span className="lime">Your coach.</span></h1><p>Get a plan for your next game, or talk through the decision that’s holding you back.</p></div>
        <section className="profile-card"><div className="section-title"><h2>Make it yours</h2><span>Change your focus to start a fresh conversation.</span></div>
          <div className="role-picker" aria-label="Choose your role">{roles.map(r => <button key={r.id} aria-pressed={profile.role === r.id} disabled={busy} onClick={() => update("role", r.id)} className={profile.role === r.id ? "active" : ""}><span>{r.symbol}</span>{r.label}</button>)}</div>
          <div className="profile-fields"><label>Your champion<input list="champions" disabled={busy} value={profile.champion} placeholder="Choose or ask generally" onChange={e => update("champion", e.target.value)}/></label><label>Opponent (optional)<input list="champions" disabled={busy} value={profile.opponent} placeholder="Who are you facing?" onChange={e => update("opponent", e.target.value)}/></label><label>Your level<select disabled={busy} value={profile.rank} onChange={e => update("rank", e.target.value)}>{["Learning", "Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master+"].map(rank => <option key={rank}>{rank}</option>)}</select></label><label>Practice focus<select disabled={busy} value={profile.goal} onChange={e => update("goal", e.target.value)}>{["Make better decisions", "Farm and wave management", "Trading and spacing", "Jungle routing", "Vision and map awareness", "Objectives and teamfights", "Play from behind"].map(goal => <option key={goal}>{goal}</option>)}</select></label></div>
          <datalist id="champions">{champions.map(c => <option key={c.id} value={c.name}/>)}</datalist>
          <div className="profile-footer"><span>{health?.catalog_version ? `Champion reference: ${health.catalog_version}` : "Champion references load after a knowledge sync"} · No game collection required</span><button className="primary" disabled={busy || restoring} onClick={() => void send("Build my pre-game guide for this role and champion. Give me a clear game plan and three practice goals.")}>Build my game plan <span>→</span></button></div>
        </section>
        {!messages.length && <div className="starter-grid">{suggestions.map((suggestion, index) => <button key={suggestion} disabled={busy} onClick={() => void send(suggestion)}><span className="starter-icon">{["↗", "◇", "◎"][index]}</span><strong>{suggestion}</strong><span className="lime">→</span></button>)}</div>}
        <section className="conversation" aria-label="Coaching conversation"><div className="section-title"><div><p className="eyebrow">✦ YOUR PRACTICE PARTNER</p><h2>{messages.length ? "Let’s work through it" : "Ask what matters to your game"}</h2></div><span className="tag">{role.label.toUpperCase()} COACH</span></div>
          {!messages.length && <div className="conversation-empty"><span>✦</span><h3>A better plan starts with a question.</h3><p>“I keep losing farm when I recall.”<br/>“How do I choose between an objective and a gank?”<br/>“What should I focus on in this matchup?”</p></div>}
          <div aria-live="polite">{messages.map((message, index) => <article key={index} className={`message ${message.role}`}><div className="speaker"><span>{message.role === "assistant" ? "✦" : "Y"}</span><strong>{message.role === "assistant" ? "LaneCoach" : "You"}</strong></div><div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>{message.sources && message.sources.length > 0 && <details className="sources"><summary>Retrieved context · {message.sources.length} references</summary>{message.sources.map(source => <div key={source.id}><strong>{source.title}</strong><small>{source.id} · {source.source_kind}{source.patch ? ` · patch ${source.patch}` : ""}</small>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">View reference ↗</a>}</div>)}</details>}{message.role === "assistant" && <button className="copy" onClick={() => {navigator.clipboard.writeText(message.content).catch(() => setError("Copy isn’t available in this browser."));}}>Copy answer</button>}</article>)}{busy && <div className="thinking" role="status"><span className="dot"/> Retrieving context and preparing your coaching…</div>}</div><div ref={bottom}/>
          <form onSubmit={submit} className="composer"><label htmlFor="question" className="sr-only">Ask your coach</label><textarea id="question" rows={2} maxLength={2000} disabled={busy} placeholder="Ask a question or follow up on your game plan…" value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => {if(e.key === "Enter" && !e.shiftKey) {e.preventDefault(); void send(question);}}}/><button className="primary" disabled={busy || !question.trim() || restoring} type="submit" aria-label="Send coaching question">↑</button></form><p className="fine-print">AI practice advice can make mistakes. Check mechanics in game. Your question and selected context go to OpenAI; API usage may incur charges.</p>
        </section>
      </>}
      {section === "evidence" && <><div className="heading"><p className="eyebrow">CONTEXT, NOT A REQUIREMENT</p><h1>The evidence behind the plan.</h1><p>You can coach without collecting games. When data exists, we show what it actually supports.</p></div><div className="stat-grid"><div><span>Stored ranked games</span><strong>{health?.matches ?? "—"}</strong></div><div><span>Role appearances</span><strong>{health?.participants ?? "—"}</strong></div><div><span>Retrievable references</span><strong>{health?.documents ?? "—"}</strong></div><div><span>Database</span><strong>{health?.engine || "—"}</strong></div></div><section className="profile-card"><h2>{profile.champion ? `${championName(profile.champion)} · ${role.label}` : "Choose a champion in Your coach"}</h2>{analytics && <><p className="evidence-note">{analytics.note}</p><p><strong>{analytics.overall.sample_size}</strong> recorded appearances · {analytics.overall.win_rate === null ? "No measured win rate" : `${analytics.overall.win_rate}% observed game wins`}</p><div className="evidence-tables"><div><h3>Observed keystone performance</h3><table><thead><tr><th>Keystone ID</th><th>Games</th><th>Game win rate</th></tr></thead><tbody>{analytics.runes.map(r => <tr key={r.keystone}><td>{r.keystone}</td><td>{r.sample_size}</td><td>{r.win_rate}%</td></tr>)}</tbody></table></div><div><h3>Observed opponents</h3><table><thead><tr><th>Opponent</th><th>Games</th><th>Your game win rate</th></tr></thead><tbody>{analytics.opponents.map(r => <tr key={r.opponent}><td>{championName(r.opponent)}</td><td>{r.sample_size}</td><td>{r.win_rate}%</td></tr>)}</tbody></table></div></div>{!analytics.overall.sample_size && <p>No stored games for this role/champion filter. Coaching still uses retrieved practice guidance and available champion references.</p>}</>}{!analytics && <p>Use the coach to choose your role and champion, then return here for available analytics.</p>}</section></>}
      {section === "about" && <><div className="heading"><p className="eyebrow">A COACH YOU CAN QUESTION</p><h1>Advice with context.</h1><p>A game plan and a conversation, for every role.</p></div><div className="about-grid"><section className="profile-card"><h2>1. Tell us your focus</h2><p>Select a role, champion, opponent and practice goal. You can also ask general questions without a matchup.</p></section><section className="profile-card"><h2>2. Retrieve relevant knowledge</h2><p>PostgreSQL full-text search retrieves role guidance and available Riot champion references. General practice notes are explicitly labelled as authored guidance.</p></section><section className="profile-card"><h2>3. Build a plan together</h2><p>OpenAI generates a practical answer from that context. Follow-up questions carry the conversation forward; the retrieved references remain inspectable.</p></section><section className="profile-card"><h2>What we won’t pretend</h2><p>A handful of wins cannot prove the best rune or a champion counter. We do not fabricate path telemetry, cooldowns or matchup statistics. Generated jungle routing advice is conditional practice guidance.</p></section></div><section className="profile-card"><h2>Connections</h2><p>PostgreSQL: {health?.database_ready ? "ready" : "not ready"} · OpenAI key: {health?.ai_configured ? "configured" : "missing"} · Riot key: {health?.riot_configured ? "configured" : "missing"}</p><p>{health?.public_demo ? "Your conversations belong to this browser. Daily request limits keep this public demo available." : "Credentials stay on the server. This is a local single-user app."}</p></section></>}
      <footer><strong>LaneCoach</strong><span>Built for better decisions.</span><span>Independent project · Not endorsed by Riot Games</span></footer>
    </main>
  </div>;
}
