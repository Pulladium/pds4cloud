import { useEffect } from "react";
import { Box, CircularProgress } from "@mui/material";

function AdminMinioPage() {
  useEffect(() => {
    window.location.assign("/minio/");
  }, []);

  return (
    <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
      <CircularProgress />
    </Box>
  );
}

export default AdminMinioPage;
