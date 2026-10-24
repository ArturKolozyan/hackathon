import { useEffect, useId, useRef, useState, type DragEvent } from "react";
import { Download, FileText, Image as ImageIcon, Paperclip, X } from "lucide-react";
import type { Receipt } from "../api";
import { HINTS } from "../hints";

const EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "heic", "heif", "webp"];
export const RECEIPT_ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.heic,.heif,.webp,application/pdf,image/jpeg,image/png,image/heic,image/heif,image/webp";
export const RECEIPT_MAX_BYTES = 10 * 1024 * 1024;
const PREVIEWABLE = new Set(["image/jpeg", "image/png", "image/webp"]);

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}

/** Same rules as the API: extension from the list and at most 10 MB. Content is checked on the server. */
export function receiptProblem(file: File): string | null {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!EXTENSIONS.includes(ext)) return "Такой файл не подходит. Подойдёт PDF, JPG, PNG, HEIC или WebP";
  if (file.size === 0) return "Файл пустой";
  if (file.size > RECEIPT_MAX_BYTES) return "Файл больше 10 МБ. Сожмите фото или PDF";
  return null;
}

function isPdf(type: string, name: string): boolean {
  return type === "application/pdf" || name.toLowerCase().endsWith(".pdf");
}

/** Браузер открывает сам только PDF и обычные картинки. HEIC и прочее отдаётся файлом. */
const OPENABLE = new Set(["application/pdf", "image/jpeg", "image/png", "image/webp"]);

/** Saved receipt: paperclip, name, size, open and download. HEIC and other types only download. */
export function ReceiptChip({ receipt, note }: { receipt: Receipt | null; note?: string | null }) {
  if (!receipt && !note) return null;
  const openable = receipt ? OPENABLE.has(receipt.content_type) : false;
  return (
    <div className="receipt-chip">
      {receipt && (
        <>
          <Paperclip size={16} strokeWidth={1.75} aria-hidden className="receipt-clip" />
          {openable ? (
            <a className="receipt-name" href={receipt.url} target="_blank" rel="noreferrer">
              {receipt.name}
            </a>
          ) : (
            <span className="receipt-name">{receipt.name}</span>
          )}
          <span className="receipt-size">{fileSize(receipt.size)}</span>
          {openable ? (
            <a
              className="icon-btn receipt-download"
              href={`${receipt.url}?download=1`}
              download={receipt.name}
              aria-label={`Скачать ${receipt.name}`}
              data-hint="Скачать файл чека"
            >
              <Download size={16} strokeWidth={1.75} aria-hidden />
            </a>
          ) : (
            <a className="ghost receipt-download-text" href={`${receipt.url}?download=1`} download={receipt.name} data-hint="Скачать файл чека">
              <Download size={16} strokeWidth={1.75} aria-hidden />
              Скачать
            </a>
          )}
        </>
      )}
      {note && <span className="receipt-note">{note}</span>}
    </div>
  );
}

/**
 * File picker for a receipt: paperclip drop zone (drag & drop on desktop),
 * then the chosen file with a preview, size, «Заменить» and «Убрать».
 */
export function ReceiptPicker({
  file,
  onFile,
  disabled,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file || !PREVIEWABLE.has(file.type)) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function take(next: File | undefined | null) {
    if (!next) return;
    const problem = receiptProblem(next);
    setError(problem);
    if (!problem) onFile(next);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDrag(false);
    if (disabled) return;
    take(event.dataTransfer.files?.[0]);
  }

  const input = (
    <input
      ref={inputRef}
      id={id}
      className="receipt-input"
      type="file"
      accept={RECEIPT_ACCEPT}
      disabled={disabled}
      onChange={(event) => take(event.target.files?.[0])}
    />
  );

  if (file) {
    return (
      <div className="receipt-picked">
        {input}
        <span className="receipt-thumb" aria-hidden="true">
          {preview ? (
            <img src={preview} alt="" />
          ) : isPdf(file.type, file.name) ? (
            <FileText size={20} strokeWidth={1.75} />
          ) : (
            <ImageIcon size={20} strokeWidth={1.75} />
          )}
        </span>
        <span className="receipt-picked-text">
          <span className="receipt-name">{file.name}</span>
          <span className="receipt-size">{fileSize(file.size)}</span>
        </span>
        <button
          type="button"
          className="ghost receipt-replace"
          disabled={disabled}
          data-hint={HINTS.receiptReplace}
          onClick={() => inputRef.current?.click()}
        >
          Заменить
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="Убрать файл"
          disabled={disabled}
          data-hint={HINTS.receiptRemove}
          onClick={() => {
            setError(null);
            onFile(null);
          }}
        >
          <X size={16} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <div className="receipt-field">
      <div
        className={drag ? "receipt-drop is-drag" : "receipt-drop"}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        {input}
        <Paperclip size={20} strokeWidth={1.75} aria-hidden className="receipt-clip" />
        <span className="receipt-drop-text">
          <span className="receipt-drop-desktop">Перетащите чек сюда или </span>
          <button
            type="button"
            className="receipt-pick"
            disabled={disabled}
            data-hint={HINTS.receiptPick}
            onClick={() => inputRef.current?.click()}
          >
            <span className="receipt-pick-desktop">выберите файл</span>
            <span className="receipt-pick-touch">Прикрепить файл</span>
          </button>
          <span className="receipt-drop-hint">PDF, JPG, PNG, HEIC или WebP, до 10 МБ</span>
        </span>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
