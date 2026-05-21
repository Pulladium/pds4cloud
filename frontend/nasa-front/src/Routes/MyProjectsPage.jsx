import { Fragment, useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Pagination,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import useProjects from "../hooks/useProjects";
import { apiFetch } from "../api/apiFetch.js";
import { useKeycloak } from "../context/KeycloakContext.jsx";
import { isResearcherOrAdmin } from "../api/auth.js";

const PAGE_SIZE = 5;
const USER_ID = "dev-user";

function hasImageError(job) {
  return Array.isArray(job?.image_progress) && job.image_progress.some((item) => item?.status === "error");
}

function statusChipProps(status, latestJob = null) {
  if (latestJob?.status === "FAILED") return { label: "failed", color: "error" };
  if (latestJob?.status === "COMPLETED" && (latestJob.error || hasImageError(latestJob))) {
    return { label: "partial", color: "warning" };
  }
  if (latestJob?.status === "COMPLETED") return { label: "finished", color: "success" };
  if (latestJob && !["COMPLETED", "FAILED"].includes(latestJob.status)) {
    return { label: "running", color: "info" };
  }

  switch (status) {
    case "not_started": return { label: "not started", color: "default" };
    case "published": return { label: "published", color: "success" };
    case "finished": return { label: "finished", color: "success" };
    case "processing":
    case "running": return { label: "running", color: "info" };
    case "failed": return { label: "failed", color: "error" };
    default: return { label: String(status), color: "default" };
  }
}

export default function MyProjectsPage() {
  const { keycloak, initialized } = useKeycloak();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [latestJobsByProject, setLatestJobsByProject] = useState({});
  const canUseProjects = initialized && keycloak?.authenticated && isResearcherOrAdmin(keycloak);
  const { projects, loading, error } = useProjects(canUseProjects, refreshKey);

  const pageCount = Math.max(1, Math.ceil(projects.length / PAGE_SIZE));
  const start = (page - 1) * PAGE_SIZE;
  const items = useMemo(() => projects.slice(start, start + PAGE_SIZE), [projects, start]);
  const itemIds = useMemo(() => items.map((project) => project.id).join("|"), [items]);

  useEffect(() => {
    if (!canUseProjects || items.length === 0) {
      setLatestJobsByProject({});
      return undefined;
    }

    let cancelled = false;
    Promise.all(
      items.map((project) =>
        apiFetch(`/api/jobs/project/${project.id}`)
          .then((response) => (response.ok ? response.json() : []))
          .then((jobs) => [project.id, Array.isArray(jobs) ? jobs[0] ?? null : null])
          .catch(() => [project.id, null])
      )
    ).then((entries) => {
      if (!cancelled) setLatestJobsByProject(Object.fromEntries(entries));
    });

    return () => {
      cancelled = true;
    };
  }, [canUseProjects, itemIds, items]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    if (!canUseProjects) {
      setCreateError(keycloak?.authenticated ? "Researcher or admin role required." : "Log in as a researcher to create projects.");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const r = await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": USER_ID },
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (!r.ok) {
        const j = await r.json();
        throw new Error(j.detail || "Failed to create project");
      }
      setCreateOpen(false);
      setNewName("");
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const response = await apiFetch(`/api/projects/${deleteTarget.id}`, {
        method: "DELETE",
        headers: { "X-User-Id": USER_ID },
      });
      if (!response.ok) {
        const json = await response.json().catch(() => ({}));
        throw new Error(json.detail || `Delete failed with HTTP ${response.status}`);
      }
      setDeleteTarget(null);
      setRefreshKey((key) => key + 1);
      setPage((current) => Math.max(1, Math.min(current, Math.ceil(Math.max(projects.length - 1, 0) / PAGE_SIZE) || 1)));
    } catch (e) {
      setDeleteError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
        <Typography variant="h3">My Projects</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateOpen(true)}
          disabled={!initialized || (keycloak?.authenticated && !canUseProjects)}
        >
          New Project
        </Button>
      </Box>

      {!initialized && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {initialized && !keycloak?.authenticated && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => keycloak?.login({ redirectUri: window.location.href })}>
              Login
            </Button>
          }
        >
          Log in as a researcher to view and create your projects.
        </Alert>
      )}

      {initialized && keycloak?.authenticated && !canUseProjects && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Your account does not have the researcher or admin role.
        </Alert>
      )}

      {canUseProjects && loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {canUseProjects && error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {canUseProjects && !loading && projects.length === 0 && !error && (
        <Typography color="text.secondary" align="center">
          No projects yet. Create one to get started.
        </Typography>
      )}

      {canUseProjects && items.length > 0 && (
        <List sx={{ borderRadius: 2, overflow: "hidden" }}>
          {items.map((a, idx) => {
            const chip = statusChipProps(a.status, latestJobsByProject[a.id]);
            return (
              <Fragment key={a.id}>
                <ListItem
                  disablePadding
                  secondaryAction={
                    <IconButton
                      edge="end"
                      aria-label={`Delete ${a.name}`}
                      onClick={() => {
                        setDeleteError("");
                        setDeleteTarget(a);
                      }}
                    >
                      <DeleteOutlineIcon />
                    </IconButton>
                  }
                >
                  <ListItemButton component={RouterLink} to={`/my-projects/${a.id}`} sx={{ py: 2 }}>
                    <ListItemText
                      primary={
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                          <Typography sx={{ fontWeight: 600 }}>{a.name}</Typography>
                          <Typography variant="caption" sx={{ fontFamily: "monospace", opacity: 0.6 }}>
                            {a.id.slice(0, 8)}…
                          </Typography>
                          <Chip size="small" {...chip} />
                        </Box>
                      }
                      secondary={`${a.image_count} image${a.image_count !== 1 ? "s" : ""} · Created: ${new Date(a.created_at).toLocaleString()}`}
                    />
                  </ListItemButton>
                </ListItem>
                {idx !== items.length - 1 && <Divider component="li" />}
              </Fragment>
            );
          })}
        </List>
      )}

      <Stack direction="row" justifyContent="center" sx={{ mt: 3 }}>
        <Pagination
          count={pageCount}
          page={page}
          onChange={(_, v) => setPage(v)}
          showFirstButton
          showLastButton
        />
      </Stack>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>New Project</DialogTitle>
        <DialogContent>
          {createError && (
            <Alert severity="error" sx={{ mt: 1, mb: 1 }}>
              {createError}
            </Alert>
          )}
          <TextField
            autoFocus
            fullWidth
            label="Project name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate} disabled={creating || !newName.trim()}>
            {creating ? <CircularProgress size={18} /> : "Create"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(deleteTarget)} onClose={() => !deleting && setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete project</DialogTitle>
        <DialogContent>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <Typography>
            Delete "{deleteTarget?.name}" and all images, chat history, and project data?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
          <Button color="error" variant="contained" onClick={handleDelete} disabled={deleting}>
            {deleting ? <CircularProgress size={18} /> : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
