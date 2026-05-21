import React from 'react';
import { Box, Typography, Grid, Container , Button} from '@mui/material';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { SpaceXBlock } from './XBlock';
import { useNavigate } from 'react-router-dom';

export function withNavigation(Component) {
  return (props) => {
    const navigate = useNavigate();
    return <Component {...props} navigate={navigate} />;
  };
}

class MarsMissionBlock extends SpaceXBlock {
  renderContent() {
    const { navigate } = this.props;

    const handleMissionsClick = () => {
        navigate('/missions');
    };
    return (
      <Grid container spacing={6} alignItems="center">
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography 
            variant="h2" 
            sx={{ 
              fontWeight: 300, 
              mb: 3,
              fontSize: { xs: '2rem', md: '2.8rem' },
              lineHeight: 1.3,
              textShadow: '0 2px 8px rgba(0,0,0,0.5)'
            }}
          >
            Currently avalible datasets
          </Typography>
        
          <Typography 
            variant="h6" 
            sx={{ 
              lineHeight: 1.8, 
              opacity: 0.9
              ,
                textAlign: 'left'
            }}
          >
            NASA's Mars 2020 Perseverance rover
          </Typography>
        
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Box sx={{ 
            border: '1px solid rgba(255,255,255,0.1)',
            p: 4,
            borderRadius: '8px',
            backgroundColor: 'rgba(0, 0, 0, 0.2)',
            backdropFilter: 'blur(4px)',
            height: '100%',
            transform: 'translateY(-10px)' // Subtle lift effect
          }}>
            <Typography 
              variant="h5" 
              sx={{ 
                fontWeight: 300, 
                mb: 3,
                letterSpacing: '1px',
                textTransform: 'uppercase',
                textAlign: 'left'
              }}
            >
              Mission Facts
            </Typography>
            <Grid container spacing={2}>
              <Grid size={6}>
                <Typography sx={{ opacity: 0.7, fontSize: '0.85rem', mb: 0.5 }}>LAUNCH DATE</Typography>
                <Typography sx={{ fontWeight: 300, fontSize: '1.1rem' }}>July 30, 2020</Typography>
              </Grid>
              <Grid size={6}>
                <Typography sx={{ opacity: 0.7, fontSize: '0.85rem', mb: 0.5 }}>LANDING DATE</Typography>
                <Typography sx={{ fontWeight: 300, fontSize: '1.1rem' }}>February 18, 2021</Typography>
              </Grid>
              <Grid size={12}>
                <Typography sx={{ opacity: 0.7, fontSize: '0.85rem', mb: 0.5 }}>LOCATION</Typography>
                <Typography sx={{ fontWeight: 300, fontSize: '1.1rem' }}>Jezero Crater, Mars</Typography>
              </Grid>
              <Grid size={6}>
                <Typography sx={{ opacity: 0.7, fontSize: '0.85rem', mb: 0.5 }}>IMAGES ANALYZED</Typography>
                <Typography sx={{ fontWeight: 300, fontSize: '1.2rem', color: '#fff' }}>1.2M+</Typography>
              </Grid>
              <Grid size={6}>
                <Typography sx={{ opacity: 0.7, fontSize: '0.85rem', mb: 0.5 }}>DISTANCE TRAVELED</Typography>
                <Typography sx={{ fontWeight: 300, fontSize: '1.2rem', color: '#fff' }}>18.5 km</Typography>
              </Grid>
            </Grid>
          </Box>
          {/* <Button 
            variant="outlined" 
            endIcon={<ArrowForwardIcon/>}
             sx={{ 
                    mt: 3, 
                    borderColor: 'white', 
                    color: 'white',
                    '&:hover': {
                    borderColor: '#ccc',
                    backgroundColor: 'rgba(255,255,255,0.1)'
                    }
                }}
            >
           Request Analizing Tool 
            </Button> */}
            <Box 
                sx={{
                    backgroundColor: 'rgba(0, 0, 0, 0.68)', // Use your #2828284a or similar
                    backdropFilter: 'blur(10px)',            // This gives the "glass" effect
                    border: '1px solid rgba(255, 255, 255, 0.1)', // Subtle outline
                    borderRadius: '8px',                     // Rounded corners
                    p: 0,                                    // Padding inside the box
                    mt: 4,                                   // Margin top to separate from facts
                    display: 'inline-flex',                         // To center the button
                    justifyContent: 'center',
                    alignItems: 'center'
                }}
                >
                <Button 
                    variant="outlined" 
                    endIcon={<ArrowForwardIcon/>}
                    sx={{ 
                    borderColor: '#ebebebd2', 
                    color:  '#ebebebd2', 
                    px: 4,                                 // Horizontal padding for the button
                    '&:hover': {
                        borderColor: '#ccc',
                        backgroundColor: 'rgba(255,255,255,0.1)'
                    }
                    }}
                    onClick={handleMissionsClick}
                >
                    Choose Mission To Analise
                </Button>
                </Box>
        </Grid>
      </Grid>
    );
  }
}

export default withNavigation(MarsMissionBlock);
