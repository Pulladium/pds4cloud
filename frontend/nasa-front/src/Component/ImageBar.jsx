import Box from '@mui/material/Box';
import { useState, useEffect } from 'react';
export default function ImageBar() {
  const imageUrl = "https://assets.science.nasa.gov/content/dam/science/psd/photojournal/pia/pia26/pia26574/PIA26574.gif";
  const heroHeight = 300;

  // Отслеживаем ширину только для аналитики или специфичных правок, 
  // для верстки здесь хватит чистого CSS
  const [windowWidth, setWindowWidth] = useState(
    typeof window !== 'undefined' ? window.innerWidth : 1024
  );

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <Box
      sx={{
        position: 'relative',
        width: '100%',
        height: heroHeight,
        backgroundColor: '#000', // Черный фон для полос по бокам
        display: 'flex',
        justifyContent: 'center', // Центрирует изображение, создавая полосы
        overflow: 'hidden',
      }}
    >
      {/* Градиент поверх изображения */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'linear-gradient(to right, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 15%, rgba(0,0,0,0) 85%, rgba(0,0,0,1) 100%)',
          pointerEvents: 'none',
          zIndex: 2,
        }}
      />
{/* --- СЛОЙ 1: Амбиентный фон (Размытое изображение) --- */}
      {/* Это создает эффект продолжения цвета к бокам */}
      <Box
        component="img"
        src={imageUrl}
        alt="" // Пустой alt для декоративного фона
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          objectFit: 'none',
          // Ключевая магия:
          // blur(40px) - сильное размытие, смешивающее цвета краев
          // brightness(0.6) - затемняем фон, чтобы главное фото выделялось
          // scale(1.2) - немного увеличиваем, чтобы скрыть резкие края самого размытия
          backdropFilter: "blur(50px)",
           filter: 'blur(3px) brightness(0.8)',
          zIndex: 0, // Самый нижний слой
          transform: 'translateZ(0)', // Хаки для производительности (активирует GPU)
            transition: 'object-position 0.3s ease',
        }}
      />
      {/* --- СЛОЙ 2: Виньетка (Градиент поверх всего) --- */}
      {/* Затемняет углы и бока, фокусируя внимание на центре */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          // Градиент от прозрачного в центре к полупрозрачному черному по бокам.
          // Это делает переход еще мягче.
          background: 'linear-gradient(to right, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0) 20%, rgba(0,0,0,0) 80%, rgba(0,0,0,0.7) 100%)',
          pointerEvents: 'none',
          zIndex: 2, // Поверх всего
        }}
      />
      <Box
        component="img"
        src={imageUrl}
        alt="Mars Perseverance"
        sx={{
          height: '100%',
          width: '100%',
          // Ограничиваем максимальную ширину, чтобы на очень широких экранах 
          // появились черные полосы (ширина подбирается под пропорции GIF)
          maxWidth: '1495px', 
          
          // cover растягивает, чтобы заполнить высоту, сохраняя пропорции
          objectFit: 'cover', 
          
          // КЛЮЧЕВОЙ МОМЕНТ: фокусируемся на голове ровера.
          // 50% - по горизонтали, 25% - фокус на верхнюю часть (где голова)
          objectPosition: '50% 25%', 
          
          transition: 'object-position 0.3s ease', // Плавность при ресайзе
          zIndex: 1,
        }}
      />
    </Box>
  );
}