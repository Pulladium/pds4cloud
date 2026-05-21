import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Grid,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import SearchIcon from "@mui/icons-material/Search";
import VisibilityIcon from "@mui/icons-material/Visibility";

function ResultCard({ result, onNavigate }) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardActionArea onClick={() => onNavigate(result)}>
        {result.thumb_url ? (
          <CardMedia
            component="img"
            height="160"
            image={result.thumb_url}
            alt={result.photo_id}
            sx={{ objectFit: "cover" }}
          />
        ) : (
          <Box sx={{ height: 160, bgcolor: "grey.800", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <ImageSearchIcon sx={{ fontSize: 48, color: "grey.500" }} />
          </Box>
        )}
        <CardContent sx={{ pb: 1 }}>
          <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" }}>
            {result.photo_id}
          </Typography>
          <Box sx={{ display: "flex", gap: 1, mt: 0.5, flexWrap: "wrap" }}>
            <Chip label={`Sol ${result.sol}`} size="small" />
            <Chip label={`${(result.score * 100).toFixed(1)}%`} size="small" color="primary" />
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

export default function VectorSearchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);
  const [textQuery, setTextQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const refLid = location.state?.ref_lid ?? null;
  useEffect(() => {
    if (refLid) {
      setTab(2);
      runSearch({ ref_lid: refLid });
    }
  }, [refLid]);

  const runSearch = async (body) => {
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const resp = await fetch("/api/qdrant/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, limit: 12 }),
      });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.detail || "Search failed");
      setResults(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTextSearch = () => {
    if (!textQuery.trim()) return;
    runSearch({ query_text: textQuery.trim() });
  };

  const handleImageUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const b64 = evt.target.result.split(",")[1];
      runSearch({ query_image_b64: b64 });
    };
    reader.readAsDataURL(file);
  };

  const handleNavigateToItem = (result) => {
    navigate(`/discover/${encodeURIComponent(result.photo_id)}`, {
      state: {
        lid:      result.lid,
        id:       result.photo_id,
        title:    `sol=${result.sol}`,
        thumbUrl: result.thumb_url,
      },
    });
  };

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>Vector Search</Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Search indexed Mars images by description, uploaded image, or visual similarity.
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab icon={<SearchIcon />} label="Text" iconPosition="start" />
        <Tab icon={<ImageSearchIcon />} label="Image Upload" iconPosition="start" />
        <Tab icon={<VisibilityIcon />} label="Find Similar" iconPosition="start" disabled={!refLid} />
      </Tabs>

      {/* Text search */}
      {tab === 0 && (
        <Box sx={{ display: "flex", gap: 2, mb: 3 }}>
          <TextField
            fullWidth
            placeholder="e.g. rocky basalt terrain, dust-covered surface, layered sediment…"
            value={textQuery}
            onChange={(e) => setTextQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleTextSearch()}
          />
          <Button
            variant="contained"
            onClick={handleTextSearch}
            disabled={loading || !textQuery.trim()}
            startIcon={loading ? <CircularProgress size={18} /> : <SearchIcon />}
            sx={{ whiteSpace: "nowrap" }}
          >
            Search
          </Button>
        </Box>
      )}

      {/* Image upload */}
      {tab === 1 && (
        <Box sx={{ mb: 3 }}>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={handleImageUpload}
          />
          <Button
            variant="outlined"
            size="large"
            startIcon={loading ? <CircularProgress size={18} /> : <ImageSearchIcon />}
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
          >
            {loading ? "Searching…" : "Upload image to search"}
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            Drag & drop or click to pick a file. Any Mars or Earth image works.
          </Typography>
        </Box>
      )}

      {/* Find similar (ref_lid) */}
      {tab === 2 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary">
            Showing images visually similar to:{" "}
            <Box component="span" sx={{ fontFamily: "monospace" }}>{refLid}</Box>
          </Typography>
          {loading && <CircularProgress size={24} sx={{ mt: 2 }} />}
        </Box>
      )}

      <Divider sx={{ mb: 3 }} />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {results.length > 0 && (
        <Grid container spacing={2}>
          {results.map((r) => (
            <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }} key={r.lid}>
              <ResultCard result={r} onNavigate={handleNavigateToItem} />
            </Grid>
          ))}
        </Grid>
      )}

      {!loading && !error && results.length === 0 && (
        <Typography color="text.secondary" sx={{ mt: 4, textAlign: "center" }}>
          No results yet. Run a search above.
        </Typography>
      )}
    </Container>
  );
}
