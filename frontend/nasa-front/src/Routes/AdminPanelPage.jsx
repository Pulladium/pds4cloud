import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import LangSmithSection from "../Component/LangSmithSection";
import { useApi } from "../api/useApi";
import { useKeycloak } from "../context/KeycloakContext";

const MISSIONS    = [{ value: "mars2020-perseverance", label: "mars2020 perseverance" }];
const INSTRUMENTS = [{ value: "mastcam-z", label: "mastcam-z" }];

function formatDuration(durationMs) {
  if (durationMs == null) return "—";
  if (durationMs < 1000) return `${durationMs} ms`;
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function ActionBox({ title, ctaLabel, onSubmit }) {
  const [mission,    setMission]    = useState(MISSIONS[0].value);
  const [instrument, setInstrument] = useState(INSTRUMENTS[0].value);
  const [from, setFrom] = useState(0);
  const [to,   setTo]   = useState(10);

  const isValid = useMemo(() => {
    const f = Number(from);
    const t = Number(to);
    return Number.isInteger(f) && Number.isInteger(t) && f >= 0 && t >= f;
  }, [from, to]);

  return (
    <Card sx={{ borderRadius: 2 }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 2 }}>{title}</Typography>
        <Stack spacing={2}>
          <FormControl fullWidth>
            <InputLabel id={`${title}-mission-label`}>Mission</InputLabel>
            <Select
              labelId={`${title}-mission-label`}
              value={mission}
              label="Mission"
              onChange={(e) => setMission(e.target.value)}
            >
              {MISSIONS.map((m) => (
                <MenuItem key={m.value} value={m.value}>{m.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel id={`${title}-instrument-label`}>Instrument</InputLabel>
            <Select
              labelId={`${title}-instrument-label`}
              value={instrument}
              label="Instrument"
              onChange={(e) => setInstrument(e.target.value)}
            >
              {INSTRUMENTS.map((ins) => (
                <MenuItem key={ins.value} value={ins.value}>{ins.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Box sx={{ display: "flex", gap: 2 }}>
            <TextField
              label="from"
              type="number"
              fullWidth
              value={from}
              onChange={(e) => setFrom(Number(e.target.value))}
              inputProps={{ step: 1 }}
            />
            <TextField
              label="to"
              type="number"
              fullWidth
              value={to}
              onChange={(e) => setTo(Number(e.target.value))}
              inputProps={{ step: 1 }}
            />
          </Box>
          {!isValid && (
            <Typography variant="caption" color="error">
              "to" must be ≥ "from", int and ≥ 0
            </Typography>
          )}
          <Button
            variant="contained"
            size="large"
            disabled={!isValid}
            onClick={() =>
              isValid && onSubmit({ mission, instrument, from: Number(from), to: Number(to) })
            }
          >
            {ctaLabel}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

function useAdminJobs() {
  const api = useApi();
  const { initialized, keycloak } = useKeycloak();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!initialized || !keycloak?.authenticated) {
      if (initialized) {
        queueMicrotask(() => {
          setLoading(false);
          setError("Please log in to view admin jobs");
        });
      }
      return;
    }

    let cancelled = false;

    api.get("/api/admin/jobs")
      .then((res) => { if (!cancelled) setJobs(res.data); })
      .catch((e) => {
        if (!cancelled) {
          console.error("Failed to load jobs:", e);
          setError(e.response?.status === 403 
            ? "Access denied: admin role required" 
            : e.message);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [api, initialized, keycloak]);

  return { jobs, loading, error };
}

function FinOpsSection() {
  const { jobs, loading, error } = useAdminJobs();

  const totals = useMemo(
    () =>
      jobs.reduce(
        (acc, j) => ({
          prompt:     acc.prompt     + (j.prompt_tokens     ?? 0),
          completion: acc.completion + (j.completion_tokens ?? 0),
          cost:       acc.cost       + (j.cost_usd          ?? 0),
        }),
        { prompt: 0, completion: 0, cost: 0 }
      ),
    [jobs]
  );

  if (loading)
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  if (error)
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        Failed to load usage data: {error}
      </Alert>
    );

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="h5" gutterBottom>
        Job History
      </Typography>
      <Divider sx={{ mb: 2 }} />

      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
        <Chip label={`Jobs: ${jobs.length}`} size="medium" variant="outlined" />
        <Chip
          label={`Prompt tokens: ${totals.prompt.toLocaleString()}`}
          size="medium"
          variant="outlined"
          color="primary"
        />
        <Chip
          label={`Completion tokens: ${totals.completion.toLocaleString()}`}
          size="medium"
          variant="outlined"
          color="secondary"
        />
        <Chip
          label={`Observed cost: $${totals.cost.toFixed(4)}`}
          size="medium"
          variant="outlined"
          color="success"
        />
      </Stack>

      {jobs.length === 0 ? (
        <Typography color="text.secondary">No jobs yet.</Typography>
      ) : (
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell>User</TableCell>
                <TableCell>Project</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Stage</TableCell>
                <TableCell>Model</TableCell>
                <TableCell align="right">Duration</TableCell>
                <TableCell align="right">Events</TableCell>
                <TableCell align="right">↑ Prompt</TableCell>
                <TableCell align="right">↓ Completion</TableCell>
                <TableCell align="right">Observed cost</TableCell>
                <TableCell align="right">Logs</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.job_id} hover>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    {job.created_at ? new Date(job.created_at).toLocaleString() : "—"}
                  </TableCell>
                  <TableCell>{job.user_id ?? "—"}</TableCell>
                  <TableCell
                    sx={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {job.project_id ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={job.status}
                      size="small"
                      color={
                        job.status === "COMPLETED"
                          ? "success"
                          : job.status === "FAILED"
                          ? "error"
                          : "default"
                      }
                    />
                  </TableCell>
                  <TableCell>{job.last_stage ?? "—"}</TableCell>
                  <TableCell>{job.model ?? "—"}</TableCell>
                  <TableCell align="right">{formatDuration(job.duration_ms)}</TableCell>
                  <TableCell align="right">{job.event_count ?? 0}</TableCell>
                  <TableCell align="right">
                    {(job.prompt_tokens ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell align="right">
                    {(job.completion_tokens ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell align="right">
                    {job.cost_usd != null ? `$${job.cost_usd.toFixed(4)}` : "—"}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      variant="outlined"
                      component={RouterLink}
                      to={`/admin/jobs/${job.job_id}/events`}
                    >
                      Events
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Box>
  );
}

export default function AdminPanelPage() {
  const [snack, setSnack] = useState("");

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        Admin Panel
      </Typography>

      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: "1fr",
          "@media (min-width: 900px)": { gridTemplateColumns: "1fr 1fr" },
          alignItems: "start",
        }}
      >
        <ActionBox
          title="Download PDS4 files"
          ctaLabel="Start PDS4 download"
          onSubmit={() => {
            setSnack("Download started (stub)");
          }}
        />
        <ActionBox
          title="Normalize and Transform Downloaded PDS4"
          ctaLabel="Start PDS4 transform"
          onSubmit={() => {
            setSnack("Transform started (stub)");
          }}
        />
      </Box>

      <FinOpsSection />
      <LangSmithSection />

      <Snackbar
        open={Boolean(snack)}
        autoHideDuration={2000}
        onClose={() => setSnack("")}
        message={snack}
      />
    </Container>
  );
}
