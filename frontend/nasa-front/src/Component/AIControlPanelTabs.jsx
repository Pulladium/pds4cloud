import { Tabs, Tab } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import { useKeycloak } from '../context/KeycloakContext.jsx';
import { isResearcherOrAdmin } from '../api/auth.js';

const tabs = [
  { label: 'Missions', path: '/missions', public: true },
  { label: 'Published', path: '/gallery', public: true },
  { label: "Discover", path: "/discover", public: true },
  { label: "MyProjects", path: "/my-projects", public: false },
  { label: "Vector Search", path: "/vector-search", public: true },
];

const AIControlPanelTabs = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { keycloak, initialized } = useKeycloak();
  const canUseProjects = initialized && keycloak?.authenticated && isResearcherOrAdmin(keycloak);
  const visibleTabs = tabs.filter((tab) => tab.public || canUseProjects);

  const currentTab = visibleTabs.findIndex(tab =>
    location.pathname.startsWith(tab.path)
  );

  const handleChange = (event, newValue) => {
    navigate(visibleTabs[newValue].path);
  };

  return (
    <Tabs
      value={currentTab === -1 ? 0 : currentTab}
      onChange={handleChange}
      sx={{
        minHeight: 64,
        '& .MuiTab-root': {
          minHeight: 64,
          color: 'rgba(255,255,255,0.7)',
        },
      }}
    >
      {visibleTabs.map(tab => (
        <Tab key={tab.path} label={tab.label} />
      ))}
    </Tabs>
  );
};
export default AIControlPanelTabs;
