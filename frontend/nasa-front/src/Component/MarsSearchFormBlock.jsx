
import React from 'react';
import {
  Box,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Grid,
  Card,
  CardMedia,
  CardActionArea,
  Typography,
  Chip,
  Paper,
  IconButton,
  CircularProgress
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import CloseIcon from '@mui/icons-material/Close';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { SpaceXBlock } from './XBlock';

export class MarsSearchFormBlock extends SpaceXBlock {
  static defaultProps = {
    ...SpaceXBlock.defaultProps,
    backgroundImage: 'https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA21040.width-1600.jpg',
    minHeight: '100vh',
    overlayOpacity: 0.3,
    blurAmount: '3px'
  };

  constructor(props) {
    super(props);
    this.state = {
      fromSol: '',
      toSol: '',
      instrument: '',
      rover: '',
      foundImages: [],
      selectedImages: [],
      isSearching: false
    };
  }

  // Mars rovers
  rovers = [
    { value: 'curiosity', label: 'Curiosity' },
    { value: 'opportunity', label: 'Opportunity' },
    { value: 'spirit', label: 'Spirit' },
    { value: 'perseverance', label: 'Perseverance' }
  ];

  // Mars rover camera instruments
  instruments = [
    { value: 'FHAZ', label: 'Front Hazard Avoidance Camera (FHAZ)' },
    { value: 'RHAZ', label: 'Rear Hazard Avoidance Camera (RHAZ)' },
    { value: 'MAST', label: 'Mast Camera (MAST)' },
    { value: 'CHEMCAM', label: 'Chemistry and Camera Complex (CHEMCAM)' },
    { value: 'MAHLI', label: 'Mars Hand Lens Imager (MAHLI)' },
    { value: 'MARDI', label: 'Mars Descent Imager (MARDI)' },
    { value: 'NAVCAM', label: 'Navigation Camera (NAVCAM)' },
    { value: 'PANCAM', label: 'Panoramic Camera (PANCAM)' },
    { value: 'MINITES', label: 'Miniature Thermal Emission Spectrometer' }
  ];

  tipImage = 'https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA21040.width-1600.jpg';

  handleSearch = async () => {
    this.setState({ isSearching: true });
    
    setTimeout(() => {
      const mockImages = [
        { 
          id: 1, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25042_PIA24542-web.jpg', 
          sol: this.state.fromSol || '1000',
          camera: this.state.instrument || 'MAST'
        },
        { 
          id: 2, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25043_PIA24543-web.jpg', 
          sol: parseInt(this.state.fromSol || '1000') + 1,
          camera: this.state.instrument || 'MAST'
        },
        { 
          id: 3, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25044_PIA24544-web.jpg', 
          sol: parseInt(this.state.fromSol || '1000') + 2,
          camera: this.state.instrument || 'NAVCAM'
        },
        { 
          id: 4, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25045_PIA24545-web.jpg', 
          sol: parseInt(this.state.fromSol || '1000') + 3,
          camera: this.state.instrument || 'NAVCAM'
        },
        { 
          id: 5, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25046_PIA24546-web.jpg', 
          sol: parseInt(this.state.fromSol || '1000') + 4,
          camera: this.state.instrument || 'FHAZ'
        },
        { 
          id: 6, 
          url: 'https://mars.nasa.gov/system/resources/detail_files/25047_PIA24547-web.jpg', 
          sol: parseInt(this.state.fromSol || '1000') + 5,
          camera: this.state.instrument || 'RHAZ'
        }
      ];
      
      this.setState({ 
        foundImages: mockImages,
        isSearching: false 
      });
    }, 1500);
  };

  handleImageSelect = (image) => {
    const { selectedImages } = this.state;
    if (selectedImages.length < 5 && !selectedImages.find(img => img.id === image.id)) {
      this.setState({
        selectedImages: [...selectedImages, image]
      });
    }
  };

  handleImageRemove = (imageId) => {
    this.setState({
      selectedImages: this.state.selectedImages.filter(img => img.id !== imageId)
    });
  };

  handleSubmit = () => {
    const { selectedImages } = this.state;
    alert(`Successfully submitted ${selectedImages.length} Mars rover images!`);
  };

  isImageSelected = (imageId) => {
    return this.state.selectedImages.some(img => img.id === imageId);
  };

  renderContent() {
    const { fromSol, toSol, instrument, rover, foundImages, selectedImages, isSearching } = this.state;

      
    return (
      <Box margin={0} padding={0}>
        <Typography 
          variant="h3" 
          gutterBottom 
          sx={{ 
            fontWeight: 'bold',
            mb: 4,
            textAlign: 'center',
            textShadow: '2px 2px 4px rgba(0,0,0,0.5)'
          }}
        >
          Mars Rover Photo Search
        </Typography>

        <Paper 
          elevation={6} 
          sx={{ 
            p: 4, 
            backgroundColor: 'rgba(0, 0, 0, 0.82)',
            backdropFilter: 'blur(5px)'
          }}
        >
          <Grid container spacing={4} sx={{ flexWrap: 'wrap', overflow: 'hidden' }}>
            {/* Column 1: Search Inputs */}
            <Grid size={{ xs: 12, md: 4 }} sx={{ minWidth: 0, maxWidth: { md: '33.33%' }, flexBasis: { md: '33.33%' } }}>
              <Box sx={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: 3,
                height: '100%',
                minWidth: 0,
                maxWidth: '100%'
              }}>
                <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }}>
                  Search Parameters
                </Typography>

                <FormControl fullWidth variant="outlined">
                  <InputLabel sx={{ color: 'white' }}>Missions (Mars Rovers Only)</InputLabel>
                  <Select
                    value={rover}
                    label="Missions (Mars Rovers Only)"
                    onChange={(e) => this.setState({ rover: e.target.value })}
                    sx={{ 
                      color: 'white',
                      '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.3)' },
                      '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'primary.main' }
                    }}
                  >
                    <MenuItem value="">
                      <em>Select a Rover</em>
                    </MenuItem>
                    {this.rovers.map((rov) => (
                      <MenuItem key={rov.value} value={rov.value}>
                        {rov.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <TextField
                  label="From Sol"
                  type="number"
                  value={fromSol}
                  onChange={(e) => this.setState({ fromSol: e.target.value })}
                  placeholder="e.g., 1000"
                  fullWidth
                  variant="outlined"
                  InputLabelProps={{ sx: { color: 'white' } }}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      color: 'white',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.3)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'primary.main' }
                    }
                  }}
                />

                <TextField
                  label="To Sol"
                  type="number"
                  value={toSol}
                  onChange={(e) => this.setState({ toSol: e.target.value })}
                  placeholder="e.g., 1100"
                  fullWidth
                  variant="outlined"
                  InputLabelProps={{ sx: { color: 'white' } }}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      color: 'white',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.3)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'primary.main' }
                    }
                  }}
                />

                <FormControl fullWidth variant="outlined">
                  <InputLabel sx={{ color: 'white' }}>Instrument (Photos Only)</InputLabel>
                  <Select
                    value={instrument}
                    label="Instrument (Photos Only)"
                    onChange={(e) => this.setState({ instrument: e.target.value })}
                    sx={{ 
                      color: 'white',
                      '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.3)' },
                      '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'primary.main' }
                    }}
                  >
                    <MenuItem value="">
                      <em>All Cameras</em>
                    </MenuItem>
                    {this.instruments.map((inst) => (
                      <MenuItem key={inst.value} value={inst.value}>
                        {inst.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Button
                  variant="contained"
                  startIcon={isSearching ? <CircularProgress size={20} color="inherit" /> : <SearchIcon />}
                  onClick={this.handleSearch}
                  disabled={isSearching}
                  fullWidth
                  size="large"
                  sx={{ 
                    mt: 'auto',
                    py: 1.5,
                    fontWeight: 'bold'
                  }}
                >
                  {isSearching ? 'Searching...' : 'Search Photos'}
                </Button>
              </Box>
            </Grid>

            {/* Column 2: Results and Selection */}
            <Grid size={{ xs: 12, md: 8 }} sx={{ minWidth: 0, maxWidth: { md: '66.66%' }, flexBasis: { md: '66.66%' } }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0, maxWidth: '100%', overflow: 'hidden' }}>
                {/* Found Images Grid */}
                <Box>
                  <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }}>
                    Found Images
                  </Typography>
                  
                  {foundImages.length === 0 ? (
                    <Box>
                      <Box sx={{ p: 3, bgcolor: 'primary.main', color: 'white', mt: 3, borderRadius: 2 }}>
                        <Typography variant="body1" sx={{ fontWeight: 'medium' }}>
                          Enter a sol range and select an instrument to find Mars rover photos.
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 1, opacity: 0.9 }}>
                          A sol is a Martian day, about 24 hours and 39 minutes.
                        </Typography>
                      </Box>
                    </Box>
                  ) : (
                    <Grid container spacing={2}>
                      {foundImages.map((image) => (
                          <Grid size={{ xs: 6, sm: 4 }} key={image.id} sx={{ minWidth: 0 }}>
                            <Card 
                              sx={{ 
                                position: 'relative',
                                cursor: 'pointer',
                                transition: 'all 0.3s',
                                maxWidth: '100%',
                                minWidth: '13em',
                                overflow: 'hidden',
                                '&:hover': {
                                  transform: 'translateY(-4px)',
                                  boxShadow: 4
                                },
                                border: this.isImageSelected(image.id) ? '3px solid' : 'none',
                                borderColor: 'success.main'
                              }}
                            >
                              <CardActionArea onClick={() => this.handleImageSelect(image)}>
                                <CardMedia
                                  component="img"
                                  height="140"
                                  image={image.url}
                                  alt={`Mars Sol ${image.sol}`}
                                  sx={{ 
                                    objectFit: 'cover',
                                    width: '100%',
                                    maxWidth: '100%'
                                  }}
                                />
                                <Box sx={{ p: 1.5, bgcolor: '#cc0808ff' }}>
                                  <Typography variant="caption" display="block" sx={{ fontWeight: 'bold' }}>
                                    Sol {image.sol}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {image.camera}
                                  </Typography>
                                </Box>
                              </CardActionArea>
                              {this.isImageSelected(image.id) && (
                                <Box
                                  sx={{
                                    position: 'absolute',
                                    top: 8,
                                    right: 8,
                                    bgcolor: 'success.main',
                                    borderRadius: '50%',
                                    p: 0.5
                                  }}
                                >
                                  <CheckCircleIcon sx={{ color: 'white', fontSize: 24 }} />
                                </Box>
                              )}
                            </Card>
                          </Grid>
                        ))}
                    </Grid>
                  )}
                </Box>

                {/* Selected Images */}
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h5" sx={{ color: 'primary.main', fontWeight: 'bold' }}>
                      Selected Images
                    </Typography>
                    <Chip 
                      label={`${selectedImages.length} / 5 selected`} 
                      color={selectedImages.length === 5 ? 'success' : 'primary'}
                      size="medium"
                      sx={{ fontWeight: 'bold' }}
                    />
                  </Box>

                  {selectedImages.length === 0 ? (
                    <Paper 
                      sx={{ 
                        p: 4, 
                        textAlign: 'center', 
                        bgcolor: 'rgba(255, 255, 255, 0.05)',
                        border: '2px dashed',
                        borderColor: 'rgba(255, 255, 255, 0.3)',
                        color: 'white'
                      }}
                    >
                      <Typography variant="body1">
                        Click on images above to select them (maximum 5 images)
                      </Typography>
                    </Paper>
                  ) : (
                    <Grid container spacing={2}>
                      {selectedImages.map((image) => (
                        <Grid size={{ xs: 6, sm: 4, md: 3 }} key={image.id} sx={{ minWidth: 0 }}>
                          <Card sx={{ position: 'relative', maxWidth: '100%', overflow: 'hidden' }}>
                            <CardMedia
                              component="img"
                              height="140"
                              image={image.url}
                              alt={`Selected Sol ${image.sol}`}
                              sx={{ 
                                objectFit: 'cover',
                                width: '100%',
                                maxWidth: '100%'
                              }}
                            />
                            <IconButton
                              size="small"
                              onClick={() => this.handleImageRemove(image.id)}
                              sx={{
                                position: 'absolute',
                                top: 4,
                                right: 4,
                                bgcolor: 'error.main',
                                color: 'white',
                                '&:hover': { 
                                  bgcolor: 'error.dark',
                                  transform: 'scale(1.1)'
                                }
                              }}
                            >
                              <CloseIcon fontSize="small" />
                            </IconButton>
                            <Box sx={{ p: 1, bgcolor: 'grey.100', textAlign: 'center' }}>
                              <Typography variant="caption" display="block" sx={{ fontWeight: 'bold' }}>
                                Sol {image.sol}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {image.camera}
                              </Typography>
                            </Box>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  )}
                </Box>
              </Box>
            </Grid>
          </Grid>

          {/* Submit Button */}
          <Box sx={{ mt: 5, textAlign: 'center' }}>
            <Button
              variant="contained"
              color="success"
              size="large"
              onClick={this.handleSubmit}
              disabled={selectedImages.length === 0}
              sx={{ 
                minWidth: 250, 
                py: 2,
                fontSize: '1.1rem',
                fontWeight: 'bold',
                boxShadow: 3,
                '&:hover': {
                  boxShadow: 6,
                  transform: 'translateY(-2px)'
                },
                transition: 'all 0.3s'
              }}
            >
              Submit Selection ({selectedImages.length})
            </Button>
          </Box>
        </Paper>
      </Box>
    );
  }
}

export default MarsSearchFormBlock;


        
