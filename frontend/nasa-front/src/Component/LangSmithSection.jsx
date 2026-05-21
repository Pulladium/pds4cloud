import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  IconButton,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import RefreshIcon from "@mui/icons-material/Refresh";
import useLangSmithStats from "../hooks/useLangSmithStats";

const LANGSMITH_URL = import.meta.env.VITE_LANGSMITH_URL ?? "https://smith.langchain.com";

function StatCard({ label, value, loading }) {
  return (
    <Card variant="outlined" sx={{ minWidth: 140, flex: 1 }}>
      <CardContent sx={{ pb: "12px !important" }}>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        {loading ? (
          <Skeleton variant="text" width={60} height={36} />
        ) : (
          <Typography variant="h5" fontWeight={700}>
            {value}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

function fmt(ms) {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtUsd(value) {
  return value != null ? `$${Number(value).toFixed(4)}` : "—";
}

export default function LangSmithSection() {
  const { data, loading, error, countdown, refresh } = useLangSmithStats();

  return (
    <Box sx={{ mt: 4 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
        <Typography variant="h5">LangSmith Observability</Typography>
        <Stack direction="row" alignItems="center" gap={1}>
          <Typography variant="caption" color="text.secondary">
            Refreshing in {countdown}s
          </Typography>
          <Tooltip title="Refresh now">
            <IconButton size="small" onClick={refresh}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Button
            size="small"
            variant="outlined"
            endIcon={<OpenInNewIcon fontSize="small" />}
            href={LANGSMITH_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open LangSmith
          </Button>
        </Stack>
      </Stack>

      <Divider sx={{ mb: 2 }} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Stat cards */}
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
        <StatCard label="Runs (7 days)" value={data?.total_runs ?? 0} loading={loading} />
        <StatCard label="Success rate" value={`${data?.success_rate ?? 0}%`} loading={loading} />
        <StatCard label="Avg latency" value={fmt(data?.avg_latency_ms)} loading={loading} />
        <StatCard label="Errors" value={data?.error_count ?? 0} loading={loading} />
        <StatCard label="Prompt tokens" value={(data?.total_prompt_tokens ?? 0).toLocaleString()} loading={loading} />
        <StatCard label="Completion tokens" value={(data?.total_completion_tokens ?? 0).toLocaleString()} loading={loading} />
        <StatCard label="Observed cost" value={fmtUsd(data?.total_observed_cost_usd)} loading={loading} />
      </Stack>

      {/* Recent runs table */}
      <Typography variant="h6" gutterBottom>
        Recent Runs
      </Typography>
      {loading && !data ? (
        <Skeleton variant="rectangular" height={200} />
      ) : !data?.recent_runs?.length ? (
        <Typography color="text.secondary">No runs yet in the last 7 days.</Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Latency</TableCell>
              <TableCell>Time</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.recent_runs.map((r) => (
              <TableRow key={r.id}>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{r.name}</TableCell>
                <TableCell>
                  <Chip
                    icon={r.status === "success" ? <CheckCircleOutlineIcon /> : <ErrorOutlineIcon />}
                    label={r.status}
                    size="small"
                    color={r.status === "success" ? "success" : "error"}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>{fmt(r.latency_ms)}</TableCell>
                <TableCell sx={{ color: "text.secondary", fontSize: 12 }}>{fmtTime(r.start_time)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  );
}
