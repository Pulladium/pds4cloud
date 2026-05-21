import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

// "pds:File.pds:file_name" -> { group: "File", field: "File Name" }
// "mars2020:Observation_Information.mars2020:sol_number" -> { group: "Observation Information", field: "Sol Number" }
// "pds:File_Area_Observational.pds:File.pds:file_name" -> { group: "File Area Observational", field: "File Name" }
function parseKey(rawKey) {
  const stripNs = (s) => (s.includes(":") ? s.slice(s.indexOf(":") + 1) : s);
  const humanize = (s) =>
    stripNs(s)
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  const parts = rawKey.split(".");
  if (parts.length === 1) {
    const label = humanize(rawKey);
    return { group: label, field: label };
  }
  return {
    group: humanize(parts[0]),
    field: humanize(parts[parts.length - 1]),
  };
}

function formatValue(val) {
  if (!Array.isArray(val)) return String(val ?? "");
  return val.join(", ");
}

function groupProperties(properties) {
  const groups = {};
  for (const [rawKey, val] of Object.entries(properties)) {
    const { group, field } = parseKey(rawKey);
    if (!groups[group]) groups[group] = [];
    groups[group].push({ field, value: formatValue(val) });
  }
  return groups;
}

export default function FullMetadataPanel({ data, loading, error }) {
  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">Failed to load full metadata: {error}</Alert>;
  }

  if (!data) return null;

  const properties =
    data.properties ??
    (Array.isArray(data.data) ? data.data[0]?.properties : data.data?.properties) ??
    {};

  const groups = groupProperties(properties);

  const handleOpenRawMetadata = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  };

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "flex-end", p: 1 }}>
        <Button
          size="small"
          variant="outlined"
          startIcon={<OpenInNewIcon />}
          onClick={handleOpenRawMetadata}
        >
          Open raw metadata
        </Button>
      </Box>
      {Object.entries(groups).map(([group, rows]) => (
        <Accordion
          key={group}
          disableGutters
          elevation={0}
          sx={{ border: "1px solid", borderColor: "divider", "&:not(:last-child)": { borderBottom: 0 } }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" fontWeight={600}>
              {group}
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            <Table size="small">
              <TableBody>
                {rows.map(({ field, value }, idx) => (
                  <TableRow key={idx}>
                    <TableCell
                      sx={{ fontWeight: 600, width: 200, borderBottom: "none" }}
                    >
                      {field}
                    </TableCell>
                    <TableCell
                      sx={{
                        fontFamily: "monospace",
                        fontSize: 13,
                        wordBreak: "break-all",
                        borderBottom: "none",
                      }}
                    >
                      {value}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}
