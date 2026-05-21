import { useState, useEffect, useCallback, useMemo } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ChatIcon from "@mui/icons-material/Chat";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ChatDrawer from "../Component/ChatDrawer";
import JobProgressPanel from "../Component/JobProgressPanel";
import PdfPanel from "../Component/PdfPanel";
import { useJobPoller } from "../hooks/useJobPoller";
import { useOpenAiModels } from "../hooks/useOpenAiModels";
import { apiFetch } from "../api/apiFetch.js";
import { gatewayUrl } from "../api/gatewayUrl.js";
import { useKeycloak } from "../context/KeycloakContext.jsx";
import { isResearcherOrAdmin } from "../api/auth.js";

const USER_ID = "dev-user";
const MAX_PUBLISH_IMAGE_BYTES = 2 * 1024 * 1024;

function analysisStatusLabel(cache) {
  if (cache?.status === "cached") return "cached";
  return "not analyzed";
}

function analyzedAtLabel(cache) {
  if (cache?.status !== "cached") return null;
  if (!cache.analyzed_at) return "unknown";
  return new Date(cache.analyzed_at).toLocaleString();
}

function discoveryStateFromProjectImage(img) {
  const id = img.lid;
  const sol = img.sol ? String(img.sol).padStart(4, "0") : "";
  return {
    id,
    lid: img.lid,
    title: sol ? `sol=${sol}` : img.lid.split(":").pop(),
    thumbUrl: img.thumb_url ?? "",
    previewSource: img.preview_source ?? null,
    browseLid: null,
  };
}

export default function MyProjectItemPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { keycloak, initialized } = useKeycloak();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [selectedModel, setSelectedModel] = useState("gpt-4o");
  const [researcherComment, setResearcherComment] = useState("");
  const [publishImages, setPublishImages] = useState([]);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState("");
  const [publishSuccess, setPublishSuccess] = useState("");
  const [latestReportUrl, setLatestReportUrl] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const canUseProjects = initialized && keycloak?.authenticated && isResearcherOrAdmin(keycloak);
  const { job, error: pollError } = useJobPoller(canUseProjects ? jobId : null);
  const { models, loading: modelsLoading } = useOpenAiModels(canUseProjects);

  const loadProject = useCallback(() => {
    if (!initialized) return;
    if (!canUseProjects) {
      setProject(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    apiFetch(`/api/projects/${id}`, { headers: { "X-User-Id": USER_ID } })
      .then((r) => {
        if (!r.ok) throw new Error(`Server responded with ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setProject(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [canUseProjects, id, initialized]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  useEffect(() => {
    if (!canUseProjects) return undefined;
    let cancelled = false;
    apiFetch(gatewayUrl(`/api/jobs/project/${id}`))
      .then((response) => {
        if (!response.ok) return [];
        return response.json();
      })
      .then((jobs) => {
        if (cancelled || !Array.isArray(jobs)) return;
        const latestCompleted = jobs.find((item) => item.status === "COMPLETED" && item.pdf_url);
        setLatestReportUrl(latestCompleted?.pdf_url ?? "");
      })
      .catch(() => {
        if (!cancelled) setLatestReportUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [canUseProjects, id]);

  useEffect(() => {
    if (job?.status === "COMPLETED") {
      setLatestReportUrl(job.pdf_url ?? "");
      loadProject();
    }
  }, [job?.pdf_url, job?.status, loadProject]);

  const handleRunAnalysis = useCallback(async () => {
    if (!project) return;
    setSubmitError(null);
    try {
      const images = project.images.map((img) => ({
        lid: img.lid,
        thumbUrl: img.thumb_url ?? "",
      }));
      const res = await apiFetch(gatewayUrl("/api/jobs"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: id, images, model: selectedModel }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobId(data.job_id);
    } catch (e) {
      setSubmitError(e.message);
    }
  }, [id, project, selectedModel]);

  const isJobActive = job && !["COMPLETED", "FAILED"].includes(job.status);
  const jobProgressByLid = useMemo(
    () => new Map(
      (Array.isArray(job?.image_progress) ? job.image_progress : [])
        .filter((item) => item.lid)
        .map((item) => [item.lid, item])
    ),
    [job?.image_progress]
  );
  const failedImages = useMemo(
    () => project?.images?.filter((img) => jobProgressByLid.get(img.lid)?.status === "error") ?? [],
    [jobProgressByLid, project?.images]
  );
  const reportUrl = job?.pdf_url ?? latestReportUrl;

  const handleRerunFailedImages = useCallback(async () => {
    if (!project || failedImages.length === 0) return;
    setSubmitError(null);
    try {
      const images = failedImages.map((img) => ({
        lid: img.lid,
        thumbUrl: img.thumb_url ?? "",
      }));
      const res = await apiFetch(gatewayUrl("/api/jobs"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: id, images, model: selectedModel }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobId(data.job_id);
    } catch (e) {
      setSubmitError(e.message);
    }
  }, [failedImages, id, project, selectedModel]);

  const handlePublishImagesChange = (event) => {
    const files = Array.from(event.target.files ?? []);
    setPublishError("");
    if (files.length > 2) {
      setPublishImages([]);
      setPublishError("You can publish at most 2 JPG or PNG images.");
      return;
    }
    const invalid = files.find((file) => {
      const typeOk = ["image/jpeg", "image/png"].includes(file.type);
      return !typeOk || file.size > MAX_PUBLISH_IMAGE_BYTES;
    });
    if (invalid) {
      setPublishImages([]);
      setPublishError("Images must be JPG or PNG files and 2 MB or smaller.");
      return;
    }
    setPublishImages(files);
  };

  const handlePublish = async () => {
    setPublishError("");
    setPublishSuccess("");
    if (!researcherComment.trim()) {
      setPublishError("Researcher comment is required.");
      return;
    }
    if (!reportUrl) {
      setPublishError("Run analysis to generate a PDF report before publishing.");
      return;
    }

    const body = new FormData();
    body.set("comment", researcherComment.trim());
    body.set("pdf_url", reportUrl);
    publishImages.forEach((file) => body.append("images", file));

    setPublishing(true);
    try {
      const response = await apiFetch(`/api/projects/${id}/publish`, {
        method: "POST",
        headers: { "X-User-Id": USER_ID },
        body,
      });
      if (!response.ok) {
        const json = await response.json().catch(() => ({}));
        throw new Error(json.detail || `Publish failed with HTTP ${response.status}`);
      }
      setPublishSuccess("Project published to gallery.");
      loadProject();
    } catch (e) {
      setPublishError(e.message);
    } finally {
      setPublishing(false);
    }
  };

  const handleDeleteProject = async () => {
    setDeleting(true);
    setDeleteError("");
    try {
      const response = await apiFetch(`/api/projects/${id}`, {
        method: "DELETE",
        headers: { "X-User-Id": USER_ID },
      });
      if (!response.ok) {
        const json = await response.json().catch(() => ({}));
        throw new Error(json.detail || `Delete failed with HTTP ${response.status}`);
      }
      navigate("/my-projects");
    } catch (e) {
      setDeleteError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 3, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Container>
    );
  }

  if (initialized && !keycloak?.authenticated) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Button startIcon={<ArrowBackIcon />} component={RouterLink} to="/my-projects" sx={{ mb: 2 }}>
          Back
        </Button>
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" onClick={() => keycloak?.login({ redirectUri: window.location.href })}>
              Login
            </Button>
          }
        >
          Log in as a researcher to view this project.
        </Alert>
      </Container>
    );
  }

  if (initialized && keycloak?.authenticated && !canUseProjects) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Button startIcon={<ArrowBackIcon />} component={RouterLink} to="/my-projects" sx={{ mb: 2 }}>
          Back
        </Button>
        <Alert severity="warning">
          Your account does not have the researcher or admin role.
        </Alert>
      </Container>
    );
  }

  if (error || !project) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Alert severity="error">{error || "Project not found"}</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <Button startIcon={<ArrowBackIcon />} component={RouterLink} to="/my-projects">
          Back
        </Button>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Typography variant="h4">{project.name}</Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <FormControl size="small" sx={{ minWidth: 160 }} disabled={modelsLoading || isJobActive}>
            <InputLabel id="model-select-label">Model</InputLabel>
            <Select
              labelId="model-select-label"
              value={selectedModel}
              label="Model"
              onChange={(e) => setSelectedModel(e.target.value)}
            >
              {(models.length > 0 ? models : ["gpt-4o"]).map((m) => (
                <MenuItem key={m} value={m}>{m}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            variant="contained"
            color="secondary"
            startIcon={<PlayArrowIcon />}
            onClick={handleRunAnalysis}
            disabled={project.images.length === 0 || isJobActive}
          >
            Run Analysis
          </Button>
          <Button
            variant="contained"
            startIcon={<ChatIcon />}
            onClick={() => setChatOpen(true)}
            disabled={project.images.length === 0}
          >
            Open Chat
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            onClick={() => {
              setDeleteError("");
              setDeleteOpen(true);
            }}
            disabled={Boolean(isJobActive)}
          >
            Delete
          </Button>
        </Box>
      </Box>

      <Typography sx={{ fontFamily: "monospace" }} color="text.secondary" gutterBottom>
        ID: {id}
      </Typography>

      {submitError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {submitError}
        </Alert>
      )}
      {pollError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Could not reach gateway: {pollError}
        </Alert>
      )}

      <JobProgressPanel job={job} />

      {failedImages.length > 0 && (
        <Alert
          severity="warning"
          sx={{ mt: 2 }}
          action={
            <Button color="inherit" size="small" onClick={handleRerunFailedImages} disabled={isJobActive}>
              Run failed images
            </Button>
          }
        >
          {failedImages.length} image{failedImages.length === 1 ? "" : "s"} failed in the latest job.
        </Alert>
      )}

      {project.images.length === 0 ? (
        <Box sx={{ mt: 2, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
          <Alert severity="info" sx={{ width: "100%" }}>
            No images in this project yet. Add images from the Discover page.
          </Alert>
          <Button variant="outlined" onClick={() => navigate("/discover")}>
            Go to Discover
          </Button>
        </Box>
      ) : (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            mt: 2,
          }}
        >
          {project.images.map((img) => {
            const imageJobProgress = jobProgressByLid.get(img.lid);
            const discoveryState = discoveryStateFromProjectImage(img);
            return (
              <Card key={img.id} sx={{ borderRadius: 2, overflow: "hidden", height: "100%" }}>
                <CardActionArea
                  component={RouterLink}
                  to={`/discover/${encodeURIComponent(img.lid)}`}
                  state={discoveryState}
                  sx={{ height: "100%", alignItems: "stretch", display: "flex", flexDirection: "column" }}
                >
                  <CardMedia
                    component="img"
                    height="160"
                    image={img.thumb_url}
                    alt={img.lid}
                    sx={{ objectFit: "cover" }}
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
                    <Typography variant="caption" color="text.secondary">
                      Added: {new Date(img.added_at).toLocaleString()}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                      Analysis: {analysisStatusLabel(img.analysis_cache)}
                    </Typography>
                    {analyzedAtLabel(img.analysis_cache) && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                        Analyzed: {analyzedAtLabel(img.analysis_cache)}
                      </Typography>
                    )}
                    {imageJobProgress?.status === "error" && (
                      <Alert severity="error" sx={{ mt: 1 }}>
                        {imageJobProgress?.error || "Image analysis failed"}
                      </Alert>
                    )}
                  </CardContent>
                </CardActionArea>
              </Card>
            );
          })}
        </Box>
      )}

      <PdfPanel pdfUrl={reportUrl} />

      <Box sx={{ mt: 3, p: 2, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
        <Typography variant="h6" gutterBottom>
          Publish to site
        </Typography>
        {publishError && <Alert severity="error" sx={{ mb: 2 }}>{publishError}</Alert>}
        {publishSuccess && <Alert severity="success" sx={{ mb: 2 }}>{publishSuccess}</Alert>}
        <Stack spacing={2}>
          <TextField
            label="Researcher comment"
            value={researcherComment}
            onChange={(e) => setResearcherComment(e.target.value)}
            multiline
            minRows={3}
            fullWidth
          />
          <Typography variant="body2" color="text.secondary">
            The latest generated PDF report will be published automatically.
          </Typography>
          <Button variant="outlined" component="label">
            Select up to 2 JPG/PNG images
            <input
              hidden
              type="file"
              accept="image/png,image/jpeg"
              multiple
              onChange={handlePublishImagesChange}
            />
          </Button>
          {publishImages.length > 0 && (
            <Typography variant="body2" color="text.secondary">
              Selected: {publishImages.map((file) => file.name).join(", ")}
            </Typography>
          )}
          <Button
            variant="contained"
            onClick={handlePublish}
            disabled={publishing || !researcherComment.trim() || !reportUrl}
          >
            {publishing ? <CircularProgress size={18} /> : "Publish"}
          </Button>
        </Stack>
      </Box>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} projectId={id} />

      <Dialog open={deleteOpen} onClose={() => !deleting && setDeleteOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete project</DialogTitle>
        <DialogContent>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <Typography>
            Delete "{project.name}" and all images, chat history, and project data?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)} disabled={deleting}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleDeleteProject} disabled={deleting}>
            {deleting ? <CircularProgress size={18} /> : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
