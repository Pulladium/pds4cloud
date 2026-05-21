import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useApi } from "../api/useApi";
import { useKeycloak } from "../context/KeycloakContext";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatDuration(durationMs) {
  if (durationMs == null) return "—";
  if (durationMs < 1000) return `${durationMs} ms`;
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export default function AdminJobEventsPage() {
  const { jobId } = useParams();
  const api = useApi();
  const { initialized, keycloak } = useKeycloak();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!initialized || !keycloak?.authenticated) {
      if (initialized) {
        queueMicrotask(() => {
          setLoading(false);
          setError("Please log in to view job events");
        });
      }
      return;
    }

    let cancelled = false;
    api.get(`/api/admin/jobs/${jobId}/events`)
      .then((res) => { if (!cancelled) setEvents(res.data ?? []); })
      .catch((e) => {
        if (!cancelled) {
          setError(e.response?.status === 403 ? "Access denied: admin role required" : e.message);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [api, initialized, keycloak, jobId]);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            Job Events
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
            {jobId}
          </Typography>
        </Box>
        <Button component={RouterLink} to="/admin" variant="outlined">
          Back
        </Button>
      </Stack>
      <Divider sx={{ mb: 2 }} />

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress />
        </Box>
      )}
      {error && <Alert severity="error">Failed to load job events: {error}</Alert>}
      {!loading && !error && events.length === 0 && (
        <Typography color="text.secondary">No events stored for this job.</Typography>
      )}
      {!loading && !error && events.length > 0 && (
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Created</TableCell>
                <TableCell>Stage</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Message</TableCell>
                <TableCell align="right">Duration</TableCell>
                <TableCell>Payload</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((event) => (
                <TableRow key={event.id} hover>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(event.created_at)}</TableCell>
                  <TableCell>{event.stage ?? "—"}</TableCell>
                  <TableCell>
                    <Chip
                      label={event.status ?? "UNKNOWN"}
                      size="small"
                      color={
                        event.status === "COMPLETED"
                          ? "success"
                          : event.status === "FAILED"
                          ? "error"
                          : "default"
                      }
                    />
                  </TableCell>
                  <TableCell sx={{ maxWidth: 260, overflowWrap: "anywhere" }}>
                    {event.message || "—"}
                  </TableCell>
                  <TableCell align="right">{formatDuration(event.duration_ms)}</TableCell>
                  <TableCell>
                    <Box
                      component="pre"
                      sx={{
                        m: 0,
                        maxWidth: 420,
                        maxHeight: 180,
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                        fontSize: 12,
                      }}
                    >
                      {event.payload_json || "{}"}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Container>
  );
}
