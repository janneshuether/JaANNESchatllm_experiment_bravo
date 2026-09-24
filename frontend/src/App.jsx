const { useEffect, useMemo, useRef, useState } = React;

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const DEFAULT_WELCOME_MESSAGE = {
  id: "welcome-msg",
  role: "assistant",
  content: "Bem-vindo ao ChatLLM Lab. Como posso ajudar voce hoje?",
};

function App() {
  const [messages, setMessages] = useState([DEFAULT_WELCOME_MESSAGE]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const messagesRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Auth state
  const [currentUser, setCurrentUser] = useState(null);
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("chatllm_token") || "");
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  // Sessions state
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Load user session on mount
  useEffect(() => {
    if (authToken) {
      authApi.getMe(authToken).then((user) => {
        if (user) {
          setCurrentUser(user);
        } else {
          setAuthToken("");
          localStorage.removeItem("chatllm_token");
        }
      }).catch(() => {
        setAuthToken("");
        localStorage.removeItem("chatllm_token");
      });
    }
  }, [authToken]);

  // Load chat sessions on mount or when token changes
  const loadSessions = async (tokenToUse = authToken) => {
    try {
      const data = await sessionApi.getSessions(tokenToUse);
      setSessions(data || []);
      if (data && data.length > 0) {
        if (!activeSessionId || !data.some(s => s.id === activeSessionId)) {
          selectSession(data[0].id, tokenToUse);
        }
      } else {
        // Create initial session if none exists
        const newSess = await sessionApi.createSession(null, tokenToUse);
        setSessions([newSess]);
        setActiveSessionId(newSess.id);
        setMessages([DEFAULT_WELCOME_MESSAGE]);
      }
    } catch (err) {
      console.error("Falha ao carregar sessoes:", err);
    }
  };

  useEffect(() => {
    loadSessions(authToken);
  }, [authToken]);

  const selectSession = async (sessionId, tokenToUse = authToken) => {
    setActiveSessionId(sessionId);
    setError("");
    try {
      const history = await sessionApi.getSessionMessages(sessionId, tokenToUse);
      if (history && history.length > 0) {
        setMessages(
          history.map((m) => ({
            id: String(m.id),
            role: m.role,
            content: m.content,
          }))
        );
      } else {
        setMessages([DEFAULT_WELCOME_MESSAGE]);
      }
    } catch (err) {
      console.error("Falha ao carregar historico da sessao:", err);
      setMessages([DEFAULT_WELCOME_MESSAGE]);
    }
  };

  const handleNewChat = async () => {
    if (busy) return;
    try {
      const newSess = await sessionApi.createSession(null, authToken);
      setSessions((prev) => [newSess, ...prev]);
      setActiveSessionId(newSess.id);
      setMessages([DEFAULT_WELCOME_MESSAGE]);
      setText("");
      setError("");
    } catch (err) {
      setError("Erro ao criar nova conversa.");
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    try {
      await sessionApi.deleteSession(sessionId, authToken);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          selectSession(remaining[0].id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Erro ao deletar sessao:", err);
    }
  };

  const handleLogout = async () => {
    const token = authToken;
    localStorage.removeItem("chatllm_token");
    setAuthToken("");
    setCurrentUser(null);
    if (token) {
      await authApi.logout(token).catch(() => {});
    }
    loadSessions("");
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthLoading(true);

    try {
      let result;
      if (authMode === "register") {
        result = await authApi.register({ email: authEmail, password: authPassword });
      } else {
        result = await authApi.login({ email: authEmail, password: authPassword });
      }

      if (result && result.token && result.user) {
        localStorage.setItem("chatllm_token", result.token);
        setAuthToken(result.token);
        setCurrentUser(result.user);
        setIsAuthModalOpen(false);
        setAuthEmail("");
        setAuthPassword("");
        loadSessions(result.token);
      }
    } catch (err) {
      setAuthError(err.message || "Erro na autenticacao.");
    } finally {
      setAuthLoading(false);
    }
  };

  const chatHistory = useMemo(
    () => messages.filter((msg) => (msg.role === "user" || msg.role === "assistant") && msg.id !== "welcome-msg"),
    [messages]
  );

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const onStop = () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setBusy(false);
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    const cleaned = text.trim();
    if (!cleaned || busy) return;

    setError("");
    const userMessage = { id: createMessageId(), role: "user", content: cleaned };
    const assistantMessageId = createMessageId();

    setMessages((prev) => {
      const filtered = prev.filter((m) => m.id !== "welcome-msg");
      return [...filtered, userMessage, { id: assistantMessageId, role: "assistant", content: "" }];
    });

    setText("");
    setBusy(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      await sendMessageStream({
        message: cleaned,
        history: chatHistory,
        sessionId: activeSessionId,
        token: authToken,
        signal: abortController.signal,
        onDelta: (delta) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: `${msg.content}${delta}` }
                : msg
            )
          );
        },
        onTitle: (newTitle) => {
          if (newTitle) {
            setSessions((prev) =>
              prev.map((s) => (s.id === activeSessionId ? { ...s, title: newTitle } : s))
            );
          }
        },
      });

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId && !msg.content.trim()
            ? { ...msg, content: "Nao foi possivel obter resposta do modelo agora." }
            : msg
        )
      );
    } catch (err) {
      const aborted = err?.name === "AbortError";
      if (!aborted) {
        setError(err.message || "Falha inesperada ao gerar resposta.");
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content.trim() ? msg.content : "Nao foi possivel obter resposta do modelo agora." }
              : msg
          )
        );
      } else {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId && !msg.content.trim()
              ? { ...msg, content: "Resposta interrompida." }
              : msg
          )
        );
      }
    } finally {
      abortControllerRef.current = null;
      setBusy(false);
    }
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <main className="app-shell">
      {/* Sidebar for chat sessions */}
      <aside className={`sidebar ${isSidebarOpen ? "" : "closed"}`}>
        <div className="sidebar-header">
          <button type="button" className="btn-new-chat" onClick={handleNewChat} title="Criar nova conversa">
            <span>+</span>
            <span>Nova conversa</span>
          </button>
        </div>

        <nav className="session-list" aria-label="Historico de conversas">
          {sessions.map((sess) => (
            <div
              key={sess.id}
              className={`session-item ${sess.id === activeSessionId ? "active" : ""}`}
              onClick={() => selectSession(sess.id)}
            >
              <span className="session-title-text" title={sess.title}>
                {sess.title || "Conversa"}
              </span>
              <button
                type="button"
                className="btn-delete-session"
                onClick={(e) => handleDeleteSession(e, sess.id)}
                title="Excluir conversa"
              >
                ✕
              </button>
            </div>
          ))}
        </nav>
      </aside>

      {/* Main chat area */}
      <section className="main-chat">
        <header className="app-header">
          <div className="header-left">
            <button
              type="button"
              className="sidebar-toggle-btn"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              title={isSidebarOpen ? "Fechar barra lateral" : "Abrir barra lateral"}
            >
              ☰
            </button>
            <div className="brand">ChatLLM Lab</div>
            {activeSession && (
              <span className="active-chat-title" title={activeSession.title}>
                • {activeSession.title}
              </span>
            )}
          </div>

          <div className="auth-controls">
            {currentUser ? (
              <>
                <div className="user-badge" title={currentUser.email}>
                  <span>👤</span>
                  <span>{currentUser.email}</span>
                </div>
                <button type="button" className="btn-logout" onClick={handleLogout}>
                  Sair
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn-auth"
                  onClick={() => {
                    setAuthMode("login");
                    setAuthError("");
                    setIsAuthModalOpen(true);
                  }}
                >
                  Entrar
                </button>
                <button
                  type="button"
                  className="btn-auth btn-auth-primary"
                  onClick={() => {
                    setAuthMode("register");
                    setAuthError("");
                    setIsAuthModalOpen(true);
                  }}
                >
                  Cadastrar
                </button>
              </>
            )}
          </div>
        </header>

        <section className="messages" aria-live="polite" ref={messagesRef}>
          <div className="messages-inner">
            {messages.map((msg) => (
              <article key={msg.id} className={`bubble ${msg.role}`}>
                <MessageContent content={msg.content} />
              </article>
            ))}
          </div>
        </section>

        <Composer
          text={text}
          busy={busy}
          error={error}
          onChangeText={setText}
          onSubmit={onSubmit}
          onStop={onStop}
        />

        <div className="warning-banner">Lembre-se, você precisa focar no experimento!!!</div>
      </section>

      {/* Auth Modal */}
      {isAuthModalOpen && (
        <div className="modal-backdrop" onClick={() => setIsAuthModalOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="modal-close"
              onClick={() => setIsAuthModalOpen(false)}
              aria-label="Fechar"
            >
              &times;
            </button>
            <div className="modal-tabs">
              <button
                type="button"
                className={`modal-tab ${authMode === "login" ? "active" : ""}`}
                onClick={() => {
                  setAuthMode("login");
                  setAuthError("");
                }}
              >
                Entrar
              </button>
              <button
                type="button"
                className={`modal-tab ${authMode === "register" ? "active" : ""}`}
                onClick={() => {
                  setAuthMode("register");
                  setAuthError("");
                }}
              >
                Cadastrar
              </button>
            </div>

            {authError && <div className="auth-error">{authError}</div>}

            <form onSubmit={handleAuthSubmit}>
              <div className="form-group">
                <label htmlFor="auth-email">E-mail</label>
                <input
                  id="auth-email"
                  type="email"
                  className="form-input"
                  required
                  placeholder="seu@email.com"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="auth-password">Senha</label>
                <input
                  id="auth-password"
                  type="password"
                  className="form-input"
                  required
                  placeholder="Sua senha"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                />
              </div>
              <button
                type="submit"
                className="form-submit"
                disabled={authLoading}
              >
                {authLoading
                  ? "Aguarde..."
                  : authMode === "login"
                  ? "Entrar"
                  : "Criar Conta"}
              </button>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
