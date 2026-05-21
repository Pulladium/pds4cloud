import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { KeycloakProvider } from './context/KeycloakContext.jsx';

const theme = createTheme({
  palette: {
    primary: {
      main: '#d84315',
      light: '#ff7043',
      dark: '#bf360c',
      contrastText: '#ffffff',
    },
    mode: 'dark',
  },
});

createRoot(document.getElementById('root')).render(
  <KeycloakProvider>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </KeycloakProvider>,
);
