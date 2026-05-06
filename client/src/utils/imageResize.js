/**
 * Resize and compress an image file to a JPEG data URL suitable for storing in DB.
 * @param {File} file
 * @param {{ maxEdge?: number, quality?: number, maxChars?: number }} opts
 * @returns {Promise<string>}
 */
export function resizeImageToJpegDataUrl(file, opts = {}) {
  const maxEdge = opts.maxEdge ?? 512;
  const maxChars = opts.maxChars ?? 900_000;
  let quality = opts.quality ?? 0.82;

  return new Promise((resolve, reject) => {
    if (!file || !file.type?.startsWith('image/')) {
      reject(new Error('Please choose an image file.'));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the file.'));
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        try {
          let w = img.naturalWidth || img.width;
          let h = img.naturalHeight || img.height;
          if (!w || !h) {
            reject(new Error('Invalid image dimensions.'));
            return;
          }
          const scale = Math.min(1, maxEdge / Math.max(w, h));
          w = Math.max(1, Math.round(w * scale));
          h = Math.max(1, Math.round(h * scale));
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            reject(new Error('Canvas not supported.'));
            return;
          }
          ctx.drawImage(img, 0, 0, w, h);
          let dataUrl = canvas.toDataURL('image/jpeg', quality);
          while (dataUrl.length > maxChars && quality > 0.35) {
            quality -= 0.1;
            dataUrl = canvas.toDataURL('image/jpeg', quality);
          }
          if (dataUrl.length > maxChars) {
            reject(new Error('Image is still too large after compression. Try a smaller image.'));
            return;
          }
          resolve(dataUrl);
        } catch (e) {
          reject(e);
        }
      };
      img.onerror = () => reject(new Error('Could not decode the image.'));
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}
