// Keep an OCR request below the hosted platform's request limit while retaining
// a document-sized image. Originals remain in the user's selected local file.
export async function prepareInvoiceImage(file){
 if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('Choose a PNG, JPEG or WebP image');
 if(file.size>15_000_000)throw Error('Choose an image below 15 MB');
 const image=await createImageBitmap(file);
 try{
  let blob=file;
  if(Math.max(image.width,image.height)>3200||file.size>2_800_000){
   const scale=Math.min(1,3200/Math.max(image.width,image.height)),canvas=document.createElement('canvas');
   canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
   const context=canvas.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,0,0,canvas.width,canvas.height);
   for(const quality of [.92,.82,.72,.62]){blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));if(blob&&blob.size<=2_800_000)break}
  }
  if(!blob||blob.size>2_800_000)throw Error('This image is too large for OCR. Crop to one readable bill and try again.');
  return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read the invoice image'));reader.readAsDataURL(blob)});
 }finally{image.close()}
}
