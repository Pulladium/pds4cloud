import { Fragment, useEffect, useState } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import {
  Alert,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Container,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  Pagination,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import GoToPageIcon from "@mui/icons-material/TravelExplore";
import ImageNotSupportedIcon from "@mui/icons-material/ImageNotSupported";
import PlaylistAddIcon from "@mui/icons-material/PlaylistAdd";
import usePds4Products from "../hooks/usePds4Products";
import AddToProjectDialog from "../Component/AddToProjectDialog";

const PAGE_SIZE = 10;
export default function DiscoverPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? "1") || 1;
  const { items, total, loading, error, indexedMaxPage } = usePds4Products(page, PAGE_SIZE);
  const [pageInput, setPageInput] = useState(String(page));
  const [dialog, setDialog] = useState(null); // { lid, thumbUrl }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    setPageInput(String(page));
  }, [page]);

  function handlePageSearchSubmit() {
    const targetPage = Number(pageInput);
    if (!Number.isInteger(targetPage) || targetPage < 1) return;
    setSearchParams({ page: String(targetPage) });
  }

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        What do we analyze today?
      </Typography>

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", my: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load products: {error}
        </Alert>
      )}

      {!loading && !error && (
        <List sx={{ bgcolor: "background.paper", borderRadius: 2, boxShadow: 1 }}>
          {items.map((p, idx) => {
            const isGeneratedPreview = p.previewSource === "generated_transform";

            return (
              <Fragment key={p.id}>
                <ListItem
                  disablePadding
                  secondaryAction={
                    <Tooltip title="Add to project">
                      <IconButton
                        edge="end"
                        size="small"
                        onClick={(e) => {
                          e.preventDefault();
                          setDialog({ lid: p.lid, thumbUrl: p.thumbUrl ?? "" });
                        }}
                      >
                        <PlaylistAddIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  }
                >
                  <ListItemButton component={RouterLink} to={`/discover/${encodeURIComponent(p.lid)}`} state={p} sx={{ pr: 7 }}>
                    <ListItemAvatar>
                      {p.thumbUrl ? (
                        <Avatar
                          variant="rounded"
                          src={p.thumbUrl}
                          alt={p.title}
                          sx={{
                            width: 96,
                            height: 54,
                            mr: 2,
                            border: isGeneratedPreview ? "2px solid #facc15" : "none",
                          }}
                        />
                      ) : (
                        <Avatar
                          variant="rounded"
                          sx={{ width: 96, height: 54, mr: 2, bgcolor: "grey.800" }}
                        >
                          <ImageNotSupportedIcon fontSize="small" />
                        </Avatar>
                      )}
                    </ListItemAvatar>

                    <ListItemText
                      primary={p.title}
                      secondary={p.id}
                      secondaryTypographyProps={{ sx: { fontFamily: "monospace" } }}
                    />
                  </ListItemButton>
                </ListItem>

                {idx !== items.length - 1 && <Divider component="li" />}
              </Fragment>
            );
          })}
        </List>
      )}

      <AddToProjectDialog
        open={Boolean(dialog)}
        onClose={() => setDialog(null)}
        lid={dialog?.lid ?? ""}
        thumbUrl={dialog?.thumbUrl ?? ""}
      />

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        alignItems="center"
        justifyContent="center"
        sx={{ mt: 2 }}
      >
        <Pagination
          count={pageCount}
          page={page}
          onChange={(_, v) => {
            setPageInput(String(v));
            setSearchParams({ page: String(v) });
          }}
          showFirstButton
          showLastButton
        />
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            label={`Page, indexed to ${indexedMaxPage ?? 1}`}
            type="number"
            size="small"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                handlePageSearchSubmit();
              }
            }}
            inputProps={{ min: 1, step: 1 }}
            sx={{ width: 170 }}
          />
          <Button
            variant="outlined"
            size="medium"
            onClick={handlePageSearchSubmit}
            startIcon={<GoToPageIcon />}
          >
            Go
          </Button>
        </Stack>
      </Stack>
    </Container>
  );
}
