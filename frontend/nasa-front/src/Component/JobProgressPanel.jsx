import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tooltip,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";

const STEPS = ["Pending", "Processing images", "Generating PDF", "Complete"];

const STATUS_STEP = {
  PENDING: 0,
  PROCESSING_IMAGES: 1,
  GENERATING_PDF: 2,
  COMPLETED: 3,
};

function parseStageInfo(stageInfo) {
  if (!stageInfo) return null;
  const [done, total] = stageInfo.split("/").map(Number);
  if (!total || isNaN(done) || isNaN(total)) return null;
  return { done, total };
}

function shortLid(lid) {
  if (!lid) return "Waiting";
  const tail = lid.split(":").pop() ?? lid;
  return tail.length > 34 ? `${tail.slice(0, 15)}...${tail.slice(-14)}` : tail;
}

function statusIcon(progress) {
  if (!progress || progress.status === "waiting") {
    return (
      <Tooltip title="Waiting">
        <HourglassEmptyIcon fontSize="small" color="disabled" />
      </Tooltip>
    );
  }
  if (progress.status === "processing") {
    return (
      <Tooltip title="Processing">
        <CircularProgress size={16} thickness={5} />
      </Tooltip>
    );
  }
  if (progress.status === "error") {
    return (
      <Tooltip title={progress.error || "Error"}>
        <ErrorOutlineIcon fontSize="small" color="error" />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="Done">
      <CheckCircleOutlineIcon fontSize="small" color="success" />
    </Tooltip>
  );
}

function contextLines(progress) {
  if (!progress || progress.status === "waiting") return [];
  const lines = [];
  if (progress.status === "done") lines.push("GPT got image");
  if (progress.metadata_loaded) lines.push("Full raw metadata");
  const bands = progress.array_summary?.bands;
  if (bands) lines.push(`PDS4 bands: ${bands}`);
  const shape = progress.array_summary?.shape;
  if (shape) lines.push(`Array: ${shape.join(" x ")}`);
  return lines;
}

function buildWorkerSlots(job) {
  const progress = Array.isArray(job.image_progress) ? job.image_progress : [];
  const parsed = parseStageInfo(job.stage_info);
  const progressByLid = new Map();
  for (const item of progress) {
    if (item.lid) progressByLid.set(item.lid, item);
  }
  const failedProgress = progress.filter((item) => item.status === "error");
  const workerCount = Math.max(
    job.worker_count ?? 0,
    progressByLid.size,
    failedProgress.length,
    parsed?.total ? Math.min(parsed.total, 6) : 0
  );
  const count = workerCount || 1;
  const visibleProgress = Array.from(progressByLid.values());

  return Array.from({ length: count }, (_, idx) => {
    const item = visibleProgress[idx];
    return item ?? { worker_id: idx, status: "waiting" };
  });
}

function WorkerProgressGrid({ job }) {
  const parsed = parseStageInfo(job.stage_info);
  const slots = buildWorkerSlots(job);
  const completedSlots = slots.filter((slot) => ["done", "error"].includes(slot.status)).length;
  const done = parsed?.done ?? completedSlots;
  const total = parsed?.total ?? Math.max(slots.length, completedSlots, 1);

  return (
    <Box sx={{ mt: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Chip label={`${done} / ${total}`} size="small" color="primary" variant="outlined" />
        <Typography variant="caption" color="text.secondary">
          Threads: {slots.length}
        </Typography>
      </Stack>
      <Box
        sx={{
          display: "grid",
          gap: 1,
          gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
        }}
      >
        {slots.map((slot, idx) => (
          <Box
            key={slot.lid ? `${slot.worker_id}:${slot.lid}` : `waiting:${slot.worker_id}:${idx}`}
            sx={{
              minHeight: 42,
              px: 1,
              py: 0.75,
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              display: "grid",
              gridTemplateColumns: "24px minmax(0, 1fr)",
              gap: 0.75,
              alignItems: "center",
            }}
          >
            <Box sx={{ display: "flex", justifyContent: "center" }}>
              {statusIcon(slot)}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" sx={{ display: "block", fontWeight: 600, lineHeight: 1.2 }}>
                Thread {slot.worker_id + 1}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                title={slot.lid || ""}
                sx={{ display: "block", fontFamily: "monospace", lineHeight: 1.2, overflow: "hidden" }}
              >
                {shortLid(slot.lid)}
              </Typography>
              {slot.status === "error" && slot.error && (
                <Typography
                  variant="caption"
                  color="error"
                  title={slot.error}
                  sx={{ display: "block", lineHeight: 1.2, overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {slot.error}
                </Typography>
              )}
              {contextLines(slot).map((line) => (
                <Typography
                  key={line}
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", lineHeight: 1.2 }}
                >
                  {line}
                </Typography>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function TokenSummary({ job }) {
  if (job.status !== "COMPLETED") return null;
  if (job.prompt_tokens == null && job.completion_tokens == null) return null;

  const prompt     = job.prompt_tokens     ?? 0;
  const completion = job.completion_tokens ?? 0;
  const total      = prompt + completion;
  const cost       = job.cost_usd != null ? `$${job.cost_usd.toFixed(4)}` : null;
  const model      = job.model ?? "gpt-4o";

  return (
    <Box sx={{ mt: 2, pt: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip label={`Model: ${model}`} size="small" variant="outlined" />
        <Chip
          label={`Tokens: ${total.toLocaleString()} (↑${prompt.toLocaleString()} / ↓${completion.toLocaleString()})`}
          size="small"
          variant="outlined"
          color="primary"
        />
        {cost && (
          <Chip label={`Observed cost: ${cost}`} size="small" variant="outlined" color="success" />
        )}
      </Stack>
    </Box>
  );
}

export default function JobProgressPanel({ job }) {
  if (!job) return null;

  const isFailed   = job.status === "FAILED";
  const isPartial  = job.status === "COMPLETED" && Boolean(job.error);
  const activeStep = STATUS_STEP[job.status] ?? 0;
  const showWorkerProgress = ["PROCESSING_IMAGES", "GENERATING_PDF", "COMPLETED", "FAILED"].includes(job.status);

  return (
    <Box sx={{ mt: 2, p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
      <Stepper activeStep={activeStep} alternativeLabel>
        {STEPS.map((label, index) => {
          const stepProps  = {};
          const labelProps = {};
          if (isFailed && index === activeStep) {
            stepProps.error  = true;
            labelProps.error = true;
          }
          return (
            <Step key={label} {...stepProps}>
              <StepLabel {...labelProps}>{label}</StepLabel>
            </Step>
          );
        })}
      </Stepper>

      {showWorkerProgress && (
        <WorkerProgressGrid job={job} />
      )}

      {isFailed && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {job.error || "Unknown error"}
        </Alert>
      )}

      {isPartial && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          {job.error}
        </Alert>
      )}

      <TokenSummary job={job} />
    </Box>
  );
}
