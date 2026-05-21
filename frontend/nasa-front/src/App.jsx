import './App.css'
import { useEffect } from 'react'
import UserAppBar from './Component/UserAppBar'
import ImageBar from './Component/ImageBar'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Alert, Box, CircularProgress } from '@mui/material'
import MarsMissionBlock from './Component/MissionsWelcomeBlock'
import PersevearenceMissionBlock from './Component/XBlock'
import MarsSearchFormBlock from './Component/MarsSearchFormBlock'
import DiscoverPage from "./Routes/DiscoverPage";
import DiscoverItemPage from "./Routes/DiscoverItemPage";
import MyProjectsPage from "./Routes/MyProjectsPage";
import MyProjectItemPage from "./Routes/MyProjectItemPage";
import AdminPanelPage from './Routes/AdminPanelPage'
import AdminJobEventsPage from './Routes/AdminJobEventsPage'
import AdminMinioPage from './Routes/AdminMinioPage'
import VectorSearchPage from "./Routes/VectorSearchPage";
import PublishedProjectsPage from "./Routes/PublishedProjectsPage";
import PublishedProjectItemPage from "./Routes/PublishedProjectItemPage";
import { useKeycloak } from './context/KeycloakContext.jsx'
import { isAdmin } from './api/auth.js'

function RequireLogin({ children }) {
  const { keycloak, initialized } = useKeycloak();

  useEffect(() => {
    if (initialized && keycloak && !keycloak.authenticated) {
      keycloak.login({ redirectUri: window.location.href });
    }
  }, [initialized, keycloak]);

  if (!initialized || !keycloak?.authenticated) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  return children;
}

function RequireAdmin({ children, fallback = "warning" }) {
  const { keycloak, initialized } = useKeycloak();

  useEffect(() => {
    if (initialized && keycloak && !keycloak.authenticated) {
      keycloak.login({ redirectUri: window.location.href });
    }
  }, [initialized, keycloak]);

  if (!initialized || !keycloak?.authenticated) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isAdmin(keycloak)) {
    if (fallback === "home") {
      return <Navigate to="/" replace />;
    }

    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Admin role required.</Alert>
      </Box>
    );
  }

  return children;
}

function App() {
  return (
    <>
    <BrowserRouter>
      <ImageBar/>
      <UserAppBar />   
       <Routes>
                <Route exact path="/"  element={
                  <MarsMissionBlock/>
                } />
                <Route exact path="/missions" element={
                  <PersevearenceMissionBlock  backgroundImage={"https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA24345.width-1600.jpg"}/>
                } />
                 <Route exact path="/analysis" element={
                  <MarsSearchFormBlock/>
                } />
                <Route path="/gallery" element={<PublishedProjectsPage />} />
                <Route path="/gallery/:id" element={<PublishedProjectItemPage />} />
                <Route path="/published-projects" element={<PublishedProjectsPage />} />

                <Route exact path="/settings" element={
                                  <MarsMissionBlock/>
                                } />

                <Route path="/discover" element={<DiscoverPage />} />
                <Route path="/discover/:id" element={<DiscoverItemPage />} />

                <Route path="/my-projects" element={<RequireLogin><MyProjectsPage /></RequireLogin>} />
                <Route path="/my-projects/:id" element={<RequireLogin><MyProjectItemPage /></RequireLogin>} />
                <Route path="/admin" element={<RequireAdmin><AdminPanelPage /></RequireAdmin>} />
                <Route path="/admin/minio" element={<RequireAdmin fallback="home"><AdminMinioPage /></RequireAdmin>} />
                <Route path="/admin/jobs/:jobId/events" element={<RequireAdmin><AdminJobEventsPage /></RequireAdmin>} />
                <Route path="/vector-search" element={<VectorSearchPage />} />
            </Routes>
    </BrowserRouter>
    </>
  )
}

export default App
