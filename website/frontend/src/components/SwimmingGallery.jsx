import React, { useState } from 'react'
import './SwimmingGallery.css'

function SwimmingGallery() {
  const [selectedImage, setSelectedImage] = useState(null)

  // Array of image filenames - shuffled
  const images = [
    'IMG_2933.JPEG',
    'IMG_4116.JPG',
    'IMG_5622.jpg',
    'IMG_2024.jpg',
    'IMG_9538.JPG',
    'IMG_0905.jpg',
    'IMG_2273.JPEG',
    'IMG_4439.jpg',
    'IMG_5113.PNG',
    'IMG_9754.JPG',
    'IMG_5219.jpg',
    'IMG_0697.JPEG',
  ]

  const openLightbox = (imageName) => {
    setSelectedImage(imageName)
  }

  const closeLightbox = () => {
    setSelectedImage(null)
  }

  return (
    <div className="gallery-page">
      <div className="gallery-container">
                <h1 className="gallery-title">Swim Gallery</h1>
        
        <div className="gallery-grid">
          {images.map((imageName, index) => {
            const isIMG5622 = imageName === 'IMG_5622.jpg';
            return (
              <div 
                key={index} 
                className={`gallery-item ${isIMG5622 ? 'gallery-item-top-crop' : ''}`}
                onClick={() => openLightbox(imageName)}
              >
                <img 
                  src={`/images/gallery/${imageName}`}
                  alt={`Swimming photo ${index + 1}`}
                  loading="lazy"
                />
                <div className="gallery-overlay">
                  <span className="gallery-icon">🔍</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {selectedImage && (
        <div className="lightbox" onClick={closeLightbox}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <button className="lightbox-close" onClick={closeLightbox}>×</button>
            <img 
              src={`/images/gallery/${selectedImage}`}
              alt="Full size"
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default SwimmingGallery

