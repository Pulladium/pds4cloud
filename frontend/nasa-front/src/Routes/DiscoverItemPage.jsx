import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ImageNotSupportedIcon from "@mui/icons-material/ImageNotSupported";
import StorageIcon from "@mui/icons-material/Storage";
import VisibilityIcon from "@mui/icons-material/Visibility";
import useFullMetadata from "../hooks/useFullMetadata";
import FullMetadataPanel from "../Component/FullMetadataPanel";
import AddToProjectDialog from "../Component/AddToProjectDialog";
import { apiFetch } from "../api/apiFetch.js";

export default function DiscoverItemPage() {
  const { state } = useLocation();
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const routeLid = routeId && routeId !== "null" && !routeId.includes(":browse:") ? routeId : null;
  const item = state ?? (routeLid ? {
    id: routeLid.split(":").pop(),
    lid: routeLid,
    title: routeLid.split(":").pop(),
    thumbUrl: "",
    browseLid: null,
    previewSource: null,
  } : null);
  const [expanded, setExpanded] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [qdrantLoading, setQdrantLoading] = useState(false);
  const [reindexDialogOpen, setReindexDialogOpen] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: "", severity: "success" });
  const { data, loading, error } = useFullMetadata(item?.lid ?? null, { enabled: expanded });

  const showSnackbar = (message, severity = "success") =>
    setSnackbar({ open: true, message, severity });

  const doAddToVectorDB = async (force = false) => {
    setQdrantLoading(true);
    try {
      const resp = await apiFetch("/api/qdrant/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lid: item.lid, thumb_url: item.thumbUrl, force }),
      });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.detail || "Unknown error");
      if (json.status === "already_indexed") {
        setReindexDialogOpen(true);
      } else {
        showSnackbar("Added to vector DB successfully.");
      }
    } catch (err) {
      showSnackbar(err.message || "Failed to add to vector DB.", "error");
    } finally {
      setQdrantLoading(false);
    }
  };

  const handleConfirmReindex = async () => {
    setReindexDialogOpen(false);
    await doAddToVectorDB(true);
  };

  const backButton = (
    <Button startIcon={<ArrowBackIcon />} onClick={() => navigate(-1)} sx={{ mb: 2 }}>
      Back
    </Button>
  );

  if (!item) {
    return (
      <Container maxWidth="md" sx={{ py: 3 }}>
        {backButton}
        <Typography>Please navigate here from the Discover list.</Typography>
      </Container>
    );
  }

  const sol = item.title?.replace("sol=", "") ?? "—";
  const isGeneratedPreview = item.previewSource === "generated_transform";

  const metaRows = [
    { label: "Sol", value: sol },
    { label: "File ID", value: item.id },
    { label: "LID", value: item.lid },
    { label: "Browse LID", value: item.browseLid ?? "—" },
  ];

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      {backButton}

      <Typography variant="h4" gutterBottom>Discover</Typography>
      <Typography sx={{ fontFamily: "monospace" }} color="text.secondary" gutterBottom>
        {item.id}
      </Typography>

      {/* Image */}
      <Box sx={{ display: "flex", justifyContent: "center", my: 3 }}>
        {item.thumbUrl ? (
          <Box
            component="img"
            src={item.thumbUrl}
            alt={item.title}
            sx={{
              maxWidth: "100%",
              maxHeight: 480,
              borderRadius: 2,
              border: isGeneratedPreview ? "3px solid #facc15" : "none",
            }}
          />
        ) : (
          <Box
            sx={{
              width: "100%", maxWidth: 480, height: 320,
              bgcolor: "grey.800", borderRadius: 2,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <ImageNotSupportedIcon sx={{ fontSize: 64, color: "grey.500" }} />
          </Box>
        )}
      </Box>

      {/* Metadata */}
      <Typography variant="h6" gutterBottom>Metadata</Typography>
      <Table size="small" sx={{ mb: 3 }}>
        <TableBody>
          {metaRows.map(({ label, value }) => (
            <TableRow key={label}>
              <TableCell sx={{ fontWeight: 600, width: 120, borderBottom: "none" }}>{label}</TableCell>
              <TableCell sx={{ fontFamily: "monospace", fontSize: 13, wordBreak: "break-all", borderBottom: "none" }}>
                {value}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Full Metadata */}
      <Accordion expanded={expanded} onChange={(_, v) => setExpanded(v)} sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6">Full Metadata</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          <FullMetadataPanel data={data} loading={loading} error={error} />
        </AccordionDetails>
      </Accordion>

      {/* Action buttons */}
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        <Button
          variant="contained"
          size="large"
          startIcon={<AddCircleOutlineIcon />}
          onClick={() => setDialogOpen(true)}
        >
          Add to project
        </Button>

        <Button
          variant="outlined"
          size="large"
          startIcon={qdrantLoading ? <CircularProgress size={18} /> : <StorageIcon />}
          onClick={() => doAddToVectorDB(false)}
          disabled={qdrantLoading || !item.thumbUrl}
        >
          Add to vector DB
        </Button>

        <Button
          variant="text"
          size="large"
          startIcon={<VisibilityIcon />}
          onClick={() => navigate("/vector-search", { state: { ref_lid: item.lid } })}
        >
          Find similar
        </Button>
      </Box>

      <AddToProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        lid={item?.lid}
        thumbUrl={item?.thumbUrl}
      />

      {/* Re-index confirmation dialog */}
      <Dialog open={reindexDialogOpen} onClose={() => setReindexDialogOpen(false)}>
        <DialogTitle>Already in vector DB</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This image is already indexed. Do you want to re-index it?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReindexDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleConfirmReindex}>Re-index</Button>
        </DialogActions>
      </Dialog>

      {/* Feedback snackbar */}
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
    </Container>
  );
}
