import { Box, Button, Typography } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";

export default function PdfPanel({ pdfUrl, showDownload = true }) {
  if (!pdfUrl) return null;

  return (
    <Box sx={{ mt: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <PictureAsPdfIcon color="error" />
        <Typography variant="h6">Analysis Report</Typography>
        {showDownload && (
          <Button
            variant="outlined"
            size="small"
            startIcon={<DownloadIcon />}
            href={pdfUrl}
            download="mars-report.pdf"
            sx={{ ml: "auto" }}
          >
            Download PDF
          </Button>
        )}
      </Box>
      <Box
        component="iframe"
        src={pdfUrl}
        sx={{ width: "100%", height: 600, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
        title="Analysis Report PDF"
      />
    </Box>
  );
}
