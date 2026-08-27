import { useState, type ChangeEvent } from "react";
import { uploadFile } from "../api/client";

interface UploadControlProps {
  onUploaded: (fileId: string, filename: string) => void;
}

export default function UploadControl({ onUploaded }: UploadControlProps) {
  const [filename, setFilename] = useState("");
  const [uploading, setUploading] = useState(false);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(file);
      setFilename(uploaded.filename);
      onUploaded(uploaded.file_id, uploaded.filename);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
      <label style={{ cursor: "pointer" }}>
        <input type="file" accept="application/pdf" onChange={handleChange} style={{ display: "none" }} />
        <span style={{ padding: "0.5rem 1rem", border: "1px solid #ccc", borderRadius: "4px" }}>
          {uploading ? "Uploading..." : "Upload PDF"}
        </span>
      </label>
      <input
        type="text"
        readOnly
        value={filename}
        placeholder="No file uploaded yet"
        style={{ flex: 1, padding: "0.5rem", color: "#555" }}
      />
    </div>
  );
}
