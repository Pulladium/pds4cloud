import { useEffect, useState } from "react";
import { Link as RouterLink, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  CircularProgress,
  Container,
  Stack,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PdfPanel from "../Component/PdfPanel";
import { apiFetch } from "../api/apiFetch.js";
import { gatewayUrl } from "../api/gatewayUrl.js";

function formatNumber(value) {
  return value == null ? "-" : Number(value).toLocaleString();
}

function formatCost(value) {
  return value == null ? "-" : `$${Number(value).toFixed(4)}`;
}

function Metric({ label, value }) {
  return (
    <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="body1">{value}</Typography>
    </Box>
  );
}

function hasMetricValues(metrics) {
  return Boolean(
    metrics?.model ||
    metrics?.prompt_tokens != null ||
    metrics?.completion_tokens != null ||
    metrics?.cost_usd != null ||
    metrics?.worker_count != null
  );
}

function metricsFromJob(job, imageCount) {
  return {
    model: job.model ?? null,
    prompt_tokens: job.prompt_tokens ?? null,
    completion_tokens: job.completion_tokens ?? null,
    cost_usd: job.cost_usd ?? null,
    worker_count: job.worker_count ?? null,
    image_count: imageCount,
  };
}

function publishedImageThumbUrl(img) {
  if (typeof img === "string") return img;
  return img.thumb_url ?? img.thumbUrl ?? img.url ?? "";
}

function discoveryStateFromPublishedImage(img) {
  const sol = img.sol ? String(img.sol).padStart(4, "0") : "";
  return {
    id: img.lid,
    lid: img.lid,
    title: sol ? `sol=${sol}` : img.lid.split(":").pop(),
    thumbUrl: publishedImageThumbUrl(img),
    previewSource: img.preview_source ?? null,
    browseLid: null,
  };
}

export default function PublishedProjectItemPage() {
  const { id } = useParams();
  const { state } = useLocation();
  const navigate = useNavigate();
  const [project, setProject] = useState(state?.project ?? null);
  const [loading, setLoading] = useState(!state?.project);
  const [error, setError] = useState("");
  const [jobMetrics, setJobMetrics] = useState(null);

  useEffect(() => {
    if (project || !id) return undefined;
    let cancelled = false;
    apiFetch("/api/projects/published")
      .then((response) => {
        if (!response.ok) throw new Error(`Server responded with ${response.status}`);
        return response.json();
      })
      .then((items) => {
        if (cancelled) return;
        const match = Array.isArray(items) ? items.find((item) => item.id === id) : null;
        if (!match) throw new Error("Published project not found");
        setProject(match);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, project]);

  useEffect(() => {
    if (!id || hasMetricValues(project?.metrics)) return undefined;
    let cancelled = false;
    apiFetch(gatewayUrl(`/api/jobs/project/${id}`))
      .then((response) => {
        if (!response.ok) return [];
        return response.json();
      })
      .then((jobs) => {
        if (cancelled || !Array.isArray(jobs)) return;
        const latestCompleted = jobs.find((job) => job.status === "COMPLETED");
        if (latestCompleted) {
          setJobMetrics(metricsFromJob(latestCompleted, project?.research_images?.length ?? project?.image_urls?.length ?? 0));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id, project?.image_urls?.length, project?.metrics, project?.research_images?.length]);

  const metrics = hasMetricValues(project?.metrics) ? project.metrics : jobMetrics ?? project?.metrics ?? {};
  const publishedAt = project?.published_at ? new Date(project.published_at).toLocaleString() : "-";
  const researchImages = project?.research_images?.length
    ? project.research_images
    : (project?.research_image_urls?.length ? project.research_image_urls : project?.image_urls ?? []).map((url) => ({
      id: url,
      lid: url,
      thumb_url: url,
      sol: "",
      added_at: "",
    }));

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 3, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Container>
    );
  }

  if (error || !project) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Button startIcon={<ArrowBackIcon />} component={RouterLink} to="/gallery" sx={{ mb: 2 }}>
          Back
        </Button>
        <Alert severity="error">{error || "Published project not found"}</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate(-1)} sx={{ mb: 2 }}>
        Back
      </Button>

      <Typography variant="h3" gutterBottom>{project.name}</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Published: {publishedAt}
      </Typography>
      {project.researcher_comment && (
        <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
          {project.researcher_comment}
        </Typography>
      )}

      {researchImages.length > 0 && (
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", mb: 3 }}>
          {researchImages.map((img) => {
            const imageThumbUrl = publishedImageThumbUrl(img);
            const isGeneratedPreview = img.preview_source === "generated_transform";
            return (
              <Card key={img.id ?? imageThumbUrl} sx={{ borderRadius: 2, overflow: "hidden", height: "100%" }}>
                <CardActionArea
                  component={RouterLink}
                  to={`/discover/${encodeURIComponent(img.lid)}`}
                  state={discoveryStateFromPublishedImage(img)}
                  sx={{ height: "100%", alignItems: "stretch", display: "flex", flexDirection: "column" }}
                >
                  <CardMedia
                    component="img"
                    height="160"
                    image={imageThumbUrl}
                    alt={img.lid}
                    sx={{
                      objectFit: "cover",
                      border: isGeneratedPreview ? "3px solid #facc15" : "none",
                    }}
                  />
                  <CardContent sx={{ py: 1.5, width: "100%" }}>
                    <Typography
                      variant="caption"
                      sx={{ fontFamily: "monospace", display: "block", wordBreak: "break-all" }}
                    >
                      {img.lid.split(":").pop()}
                    </Typography>
                    {img.sol && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                        Sol: {img.sol}
                      </Typography>
                    )}
                    {img.added_at && (
                      <Typography variant="caption" color="text.secondary">
                        Added: {new Date(img.added_at).toLocaleString()}
                      </Typography>
                    )}
                  </CardContent>
                </CardActionArea>
              </Card>
            );
          })}
        </Box>
      )}

      <Typography variant="h6" gutterBottom>Run metrics</Typography>
      <Stack
        sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", mb: 3 }}
      >
        <Metric label="Model" value={metrics.model ?? "-"} />
        <Metric label="Prompt tokens" value={formatNumber(metrics.prompt_tokens)} />
        <Metric label="Completion tokens" value={formatNumber(metrics.completion_tokens)} />
        <Metric label="Observed cost" value={formatCost(metrics.cost_usd)} />
        <Metric label="Images used" value={formatNumber(metrics.image_count ?? researchImages.length)} />
        <Metric label="Workers" value={formatNumber(metrics.worker_count)} />
      </Stack>

      <PdfPanel pdfUrl={project.pdf_url} showDownload={false} />
    </Container>
  );
}
