import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f8fafc",
        padding: "2rem",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}>
        <div style={{
          maxWidth: 480,
          background: "#fff",
          border: "1px solid #fecaca",
          borderRadius: 12,
          padding: "2rem",
          boxShadow: "0 1px 3px rgba(0,0,0,.08)",
        }}>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#991b1b", margin: "0 0 .5rem" }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: 14, color: "#6b7280", margin: "0 0 1rem", lineHeight: 1.5 }}>
            The application hit an unexpected error. Try refreshing the page.
            If the problem persists, contact support.
          </p>
          <pre style={{
            fontSize: 12,
            color: "#dc2626",
            background: "#fef2f2",
            padding: "0.75rem",
            borderRadius: 8,
            overflow: "auto",
            maxHeight: 120,
            margin: "0 0 1rem",
          }}>
            {this.state.error?.message || "Unknown error"}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: "#dc2626",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "0.5rem 1.25rem",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Reload Page
          </button>
        </div>
      </div>
    );
  }
}
