import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardMedia,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CloseIcon from "@mui/icons-material/Close";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import SendIcon from "@mui/icons-material/Send";
import useChat from "../hooks/useChat";

const DEFAULT_PROMPT =
  "You are a Mars mission scientist. Examine all images in this project using their thumbnails " +
  "and scientific metadata. Provide a mission briefing: key geological findings, spectral " +
  "observations, anomalies detected, cross-image patterns, and recommended follow-up observations.";

function ImageResultCard({ result }) {
  const navigate = useNavigate();
  const handleClick = () => {
    navigate(`/discover/${encodeURIComponent(result.photo_id)}`, {
      state: {
        lid: result.lid,
        id: result.photo_id,
        title: `sol=${result.sol}`,
        thumbUrl: result.thumb_url,
      },
    });
  };
  return (
    <Card sx={{ width: 140, flexShrink: 0, cursor: "pointer" }} onClick={handleClick}>
      <CardMedia component="img" height="90" image={result.thumb_url} alt={result.photo_id} sx={{ objectFit: "cover" }} />
      <CardContent sx={{ p: 1, "&:last-child": { pb: 1 } }}>
        <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: 10, display: "block", wordBreak: "break-all" }}>
          {result.photo_id}
        </Typography>
        <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap" }}>
          <Chip label={`Sol ${result.sol}`} size="small" sx={{ fontSize: 10, height: 18 }} />
          <Chip label={`${(result.score * 100).toFixed(1)}%`} size="small" color="primary" sx={{ fontSize: 10, height: 18 }} />
        </Box>
      </CardContent>
    </Card>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const hasImages = Array.isArray(message.image_results) && message.image_results.length > 0;
  return (
    <Box sx={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", mb: 1.5 }}>
      <Box sx={{ maxWidth: "90%" }}>
        {/* Text bubble */}
        <Box sx={{ px: 2, py: 1.25, borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          bgcolor: isUser ? "primary.main" : "rgba(255,255,255,0.08)",
          color: isUser ? "primary.contrastText" : "text.primary",
          whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.6 }}>
          {message.content}
        </Box>
        {/* Image result cards */}
        {hasImages && (
          <Box sx={{ display: "flex", gap: 1, mt: 1, overflowX: "auto", pb: 0.5 }}>
            {message.image_results.map((r) => (
              <ImageResultCard key={r.lid} result={r} />
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}

export default function ChatDrawer({ open, onClose, projectId }) {
  const { messages, loading, error, sendMessage, clearHistory } = useChat(projectId, open);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = () => {
    sendMessage(input);
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, display: "flex", flexDirection: "column" } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <Typography variant="h6">Project Chat</Typography>
        <Box sx={{ display: "flex", gap: 0.5 }}>
          <Tooltip title="Clear conversation">
            <IconButton size="small" onClick={clearHistory} disabled={messages.length === 0}>
              <DeleteSweepIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {messages.length === 0 && !loading && (
          <Typography color="text.secondary" variant="body2" align="center" sx={{ mt: 4 }}>
            Ask a question about the project images, or click Analyze Project for a full mission briefing.
          </Typography>
        )}

        {messages.map((m, idx) => (
          <MessageBubble key={idx} message={m} />
        ))}

        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1, mb: 1 }}>
            <CircularProgress size={16} />
            <Typography variant="caption" color="text.secondary">
              Analyzing…
            </Typography>
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}

        <div ref={bottomRef} />
      </Box>

      <Divider />

      {/* Analyze Project button */}
      <Box sx={{ px: 2, pt: 1.5 }}>
        <Button
          fullWidth
          variant="outlined"
          startIcon={<AutoAwesomeIcon />}
          onClick={() => sendMessage(DEFAULT_PROMPT)}
          disabled={loading}
          size="small"
        >
          Analyze Project
        </Button>
      </Box>

      {/* Input */}
      <Box sx={{ px: 2, py: 1.5, display: "flex", gap: 1 }}>
        <TextField
          fullWidth
          multiline
          maxRows={4}
          placeholder="Ask about the images…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          size="small"
        />
        <IconButton
          color="primary"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? <CircularProgress size={20} /> : <SendIcon />}
        </IconButton>
      </Box>
    </Drawer>
  );
}
