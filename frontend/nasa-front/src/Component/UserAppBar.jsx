import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import { styled } from '@mui/material/styles';
import MarsIcon from '../assets/Mars100-icon2.svg?react';
import AIControlPanelTabs from './AIControlPanelTabs';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMediaQuery } from '@mui/material';
import { useKeycloak } from '../context/KeycloakContext.jsx';

const SpaceAppBar = styled(AppBar)(() => ({
  backgroundColor: 'rgba(0, 0, 0, 0.67)',
  boxShadow: 'none',
  backdropFilter: 'blur(10px)',
  position: 'sticky',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 1000,
}));

export default function UserAppBar() {
  const location = useLocation();
  const isMobile = useMediaQuery((theme) => theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const { keycloak, initialized } = useKeycloak();
  const currentUrl = window.location.href;
  const homeUrl = window.location.origin + '/';

  const handleLogoClick = () => {
    navigate('/');
  };

  return (
    <Box sx={{ maxWidth: 1495, mx: 'auto' }}>
      <SpaceAppBar>
        <Toolbar sx={{ justifyContent: isMobile ? 'space-between' : 'flex', width: '100%' }}>
          <IconButton
            onClick={handleLogoClick}
            sx={{ width: '5vh', height: '5vh', p: 0 }}
          >
            <MarsIcon style={{ width: '100%', height: '100%' }} />
          </IconButton>

          {(
            location.pathname === '/missions' ||
            location.pathname === '/analysis' ||
            location.pathname === '/settings' ||
            location.pathname === '/gallery' ||
            location.pathname.startsWith('/discover') ||
            location.pathname.startsWith('/my-projects') ||
            location.pathname.startsWith('/admin') ||
            location.pathname.startsWith('/vector-search')
          ) && (
            <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center', ml: isMobile ? 0 : 2 }}>
              <AIControlPanelTabs currentTab={0} />
            </Box>
          )}

          {initialized && !keycloak.authenticated && (
            <Box sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
              <Button color="inherit" onClick={() => keycloak.login({ redirectUri: currentUrl })}>
                Login
              </Button>
              <Button color="inherit" onClick={() => keycloak.register({ redirectUri: currentUrl })}>
                Register
              </Button>
            </Box>
          )}

          {initialized && keycloak.authenticated && (
            <Button color="inherit" onClick={() => keycloak.logout({ redirectUri: homeUrl })}>
              Logout
            </Button>
          )}
        </Toolbar>
      </SpaceAppBar>
    </Box>
  );
}
