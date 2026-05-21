import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
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
  Snackbar,
  TextField,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import useProjects from "../hooks/useProjects";
import { apiFetch } from "../api/apiFetch.js";
import { useKeycloak } from "../context/KeycloakContext.jsx";
import { isResearcherOrAdmin } from "../api/auth.js";

const STATUS_LABEL = {
  not_started: "not started",
  published: "published",
  finished: "finished",
  processing: "running",
  running: "running",
  failed: "failed",
};
const STATUS_COLOR = {
  not_started: "default",
  published: "success",
  finished: "success",
  processing: "info",
  running: "info",
  failed: "error",
};
const USER_ID = "dev-user";

export default function AddToProjectDialog({ open, onClose, lid, thumbUrl }) {
  const { keycloak, initialized } = useKeycloak();
  const canUseProjects = initialized && keycloak?.authenticated && isResearcherOrAdmin(keycloak);
  const { projects, loading, error } = useProjects(open && canUseProjects);
  const [adding, setAdding] = useState(null); // project id being added to
  const [newProjectName, setNewProjectName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [snackbar, setSnackbar] = useState({ open: false, message: "", severity: "success" });

  const addImageToProject = async (project) => {
    setAdding(project.id);
    const r = await apiFetch(`/api/projects/${project.id}/images`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-User-Id": USER_ID },
      body: JSON.stringify({ lid, thumb_url: thumbUrl }),
    });
    const json = await r.json();
    if (!r.ok) throw new Error(json.detail || "Failed to add image");
    setSnackbar({
      open: true,
      message: json.index_warning
        ? `Added to "${project.name}". ${json.index_warning}`
        : `Added to "${project.name}"`,
      severity: json.index_warning ? "warning" : "success",
    });
    onClose();
  };

  const handleSelect = async (project) => {
    if (!canUseProjects) return;
    try {
      await addImageToProject(project);
    } catch (e) {
      setSnackbar({ open: true, message: e.message, severity: "error" });
    } finally {
      setAdding(null);
    }
  };

  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!canUseProjects || !name) return;
    setCreating(true);
    setCreateError("");
    try {
      const r = await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": USER_ID },
        body: JSON.stringify({ name }),
      });
      const created = await r.json();
      if (!r.ok) throw new Error(created.detail || "Failed to create project");
      await addImageToProject(created);
      setNewProjectName("");
    } catch (e) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
      setAdding(null);
    }
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          Add to project
          <IconButton onClick={onClose} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>

        <DialogContent dividers sx={{ p: 0 }}>
          {open && !initialized && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={32} />
            </Box>
          )}

          {initialized && !keycloak?.authenticated && (
            <Alert severity="info" sx={{ m: 2 }}>
              Log in as a researcher to add images to projects.
            </Alert>
          )}

          {initialized && keycloak?.authenticated && !canUseProjects && (
            <Alert severity="warning" sx={{ m: 2 }}>
              Your account does not have the researcher or admin role.
            </Alert>
          )}

          {canUseProjects && loading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={32} />
            </Box>
          )}

          {canUseProjects && error && (
            <Alert severity="error" sx={{ m: 2 }}>
              {error}
            </Alert>
          )}

          {canUseProjects && !loading && !error && projects.length === 0 && (
            <Box sx={{ p: 2 }}>
              <Typography color="text.secondary" sx={{ mb: 2 }}>
                No projects found. Create one here to add this image.
              </Typography>
              {createError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {createError}
                </Alert>
              )}
              <TextField
                autoFocus
                fullWidth
                label="Project name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
              />
            </Box>
          )}

          {canUseProjects && !loading && projects.length > 0 && (
            <>
              <List disablePadding>
                {projects.map((p, idx) => (
                  <Box key={p.id}>
                    <ListItem disablePadding>
                      <ListItemButton onClick={() => handleSelect(p)} disabled={adding === p.id}>
                        <ListItemText
                          primary={
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {p.name}
                              </Typography>
                              <Chip
                                label={STATUS_LABEL[p.status] ?? String(p.status)}
                                size="small"
                                color={STATUS_COLOR[p.status] ?? "default"}
                              />
                            </Box>
                          }
                          secondary={`${p.image_count}/5 images`}
                        />
                        {adding === p.id && <CircularProgress size={18} sx={{ ml: 1 }} />}
                      </ListItemButton>
                    </ListItem>
                    {idx !== projects.length - 1 && <Divider component="li" />}
                  </Box>
                ))}
              </List>
              <Divider />
              <Box sx={{ p: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  New project
                </Typography>
                {createError && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {createError}
                  </Alert>
                )}
                <TextField
                  fullWidth
                  label="Project name"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
                />
              </Box>
            </>
          )}
        </DialogContent>

        {canUseProjects && !loading && !error && (
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button
              variant="contained"
              onClick={handleCreateProject}
              disabled={creating || adding != null || !newProjectName.trim()}
            >
              {creating ? <CircularProgress size={18} /> : "Create and add"}
            </Button>
          </DialogActions>
        )}
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar((s) => ({ ...s, open: false }))}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </>
  );
}
