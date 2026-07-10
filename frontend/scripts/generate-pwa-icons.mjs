import sharp from "sharp";
import { fileURLToPath } from "node:url";

const source = fileURLToPath(new URL("../public/assets/zvezda-emblem.jpg", import.meta.url));
const output = new URL("../public/assets/icons/", import.meta.url);

await sharp(source)
  .resize(192, 192, { fit: "cover" })
  .png({ compressionLevel: 9, palette: true })
  .toFile(fileURLToPath(new URL("pwa-192.png", output)));

await sharp(source)
  .resize(512, 512, { fit: "cover" })
  .png({ compressionLevel: 9, palette: true })
  .toFile(fileURLToPath(new URL("pwa-512.png", output)));

await sharp(source)
  .resize(384, 384, { fit: "contain" })
  .extend({ top: 64, right: 64, bottom: 64, left: 64, background: "#1c2b61" })
  .png({ compressionLevel: 9, palette: true })
  .toFile(fileURLToPath(new URL("pwa-maskable-512.png", output)));
