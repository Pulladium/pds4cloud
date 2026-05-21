import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  CircularProgress,
  Container,
  Stack,
  Typography,
} from "@mui/material";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import { Link as RouterLink } from "react-router-dom";
import { apiFetch } from "../api/apiFetch.js";

export default function PublishedProjectsPage() {
  const [state, setState] = useState({ items: [], loading: true, error: "" });

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/projects/published")
      .then((response) => {
        if (!response.ok) throw new Error(`Server responded with ${response.status}`);
        return response.json();
      })
      .then((items) => {
        if (!cancelled) {
          setState({ items: Array.isArray(items) ? items : [], loading: false, error: "" });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setState({ items: [], loading: false, error: error.message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h3" gutterBottom>
        Published research
      </Typography>

      {state.loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {state.error && <Alert severity="error" sx={{ mb: 2 }}>{state.error}</Alert>}

      {!state.loading && !state.error && state.items.length === 0 && (
        <Typography color="text.secondary">No published projects yet.</Typography>
      )}

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
        {state.items.map((project) => {
          const imageUrls = project.research_image_urls?.length ? project.research_image_urls : project.image_urls;
          return (
          <Card key={project.id} sx={{ borderRadius: 1 }}>
            <CardActionArea
              component={RouterLink}
              to={`/gallery/${encodeURIComponent(project.id)}`}
              state={{ project }}
              sx={{ height: "100%", alignItems: "stretch", display: "flex", flexDirection: "column" }}
            >
              {imageUrls?.[0] && (
                <CardMedia
                  component="img"
                  height="180"
                  image={imageUrls[0]}
                  alt={project.name}
                  sx={{ objectFit: "cover" }}
                />
              )}
              <CardContent sx={{ width: "100%" }}>
                <Typography variant="h6">{project.name}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {project.researcher_comment}
                </Typography>
                {imageUrls?.length > 1 && (
                  <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                    {imageUrls.slice(1).map((url) => (
                      <Box
                        key={url}
                        component="img"
                        src={url}
                        alt=""
                        sx={{ width: 92, height: 64, objectFit: "cover", borderRadius: 1 }}
                      />
                    ))}
                  </Stack>
                )}
                {project.pdf_url && (
                  <Button
                    component="span"
                    startIcon={<PictureAsPdfIcon />}
                    sx={{ mt: 2 }}
                  >
                    Preview report
                  </Button>
                )}
              </CardContent>
            </CardActionArea>
          </Card>
          );
        })}
      </Box>
    </Container>
  );
}
