import React from 'react';
import { Box, Typography, Grid, Container , Button} from '@mui/material';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';

// Base abstract class for SpaceX-style blocks
export class SpaceXBlock extends React.Component {
  static defaultProps = {
    backgroundImage: 'https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA23764.width-1280.jpg',
    minHeight: '80vh',
    overlayOpacity: 0.4,
    blurAmount: '2px' // Reduced blur for better readability
  };

  renderContent() {
    return null; // To be implemented by child classes
  }

  render() {
    const { backgroundImage, minHeight, overlayOpacity, blurAmount } = this.props;

    return (
      <Box
        sx={{
          position: 'relative',
          minHeight: minHeight,
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          color: 'white',
        }}
      >
        {/* Background with subtle overlay and minimal blur */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: `rgba(0, 0, 0, ${overlayOpacity})`,
              backdropFilter: `blur(${blurAmount})`, // Much more subtle blur
            },
          }}
        />
        
        {/* Content container with proper alignment */}
        <Container 
          maxWidth="1590px"
          sx={{
            position: 'relative',
            px: { xs: 2, sm: 4 },
            py: { xs: 6, md: 8 },
            zIndex: 2,
          }}
        >
          {this.renderContent()}
        </Container>
      </Box>
    );
  }
}

// Specific implementation for Mars mission


class PersevearenceMissionBlock extends SpaceXBlock {
  renderContent() {
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
            Mars 2020 Perseverance
          </Typography>
          <Typography 
            variant="body1" 
            sx={{ 
              lineHeight: 1.8, 
              opacity: 0.95,
              mb: 3,
              fontSize: '1.1rem'
              ,
                textAlign: 'left'
            }}
          >
            NASA's Mars 2020 Perseverance rover landed in Jezero Crater on February 18, 2021. This mission seeks signs of ancient microbial life and collects samples of Martian rock and regolith for future return to Earth.
          </Typography>
          <Typography 
            variant="body1" 
            sx={{ 
              lineHeight: 1.8, 
              opacity: 0.9
              ,
                textAlign: 'left'
            }}
          >
            The rover explores an ancient river delta that once flowed into a lake, providing an ideal environment to search for preserved biosignatures.
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
            <Button 
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
                Start Ai Analize
            </Button>
        </Grid>
      </Grid>
    );
  }
}

export default PersevearenceMissionBlock;
