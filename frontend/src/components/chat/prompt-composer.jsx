import { Globe, Mic, Paperclip, Send, Upload, X } from 'lucide-react'
import { useId, useRef, useState } from 'react'

import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { ModelSelector } from './model-selector'

export function PromptComposer({
  attachments,
  micError,
  micSupported,
  model,
  models,
  onAttachmentsChange,
  onMicToggle,
  onModelChange,
  onSubmit,
  onTextChange,
  onWebToggle,
  status,
  text,
  useMic,
  useWeb,
}) {
  const fileInputId = useId()
  const fileRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const canSubmit = text.trim().length > 0 || attachments.length > 0

  const mapAttachments = (fileList) =>
    Array.from(fileList ?? []).map((file) => ({
      id: `${file.name}-${file.lastModified}`,
      name: file.name,
      file,
    }))

  const mergeAttachments = (incoming) => {
    if (!incoming.length) return attachments
    const seen = new Set(attachments.map((file) => file.id))
    const merged = [...attachments]
    incoming.forEach((file) => {
      if (seen.has(file.id)) return
      seen.add(file.id)
      merged.push(file)
    })
    return merged
  }

  const handleFiles = (fileList) => {
    const incoming = mapAttachments(fileList)
    if (!incoming.length) return
    onAttachmentsChange(mergeAttachments(incoming))
  }

  return (
    <div className="space-y-4">
      {attachments.length ? (
        <div className="flex flex-wrap gap-2">
          {attachments.map((file) => (
            <Badge className="gap-2 bg-slate-100 text-slate-700" key={file.id}>
              <Paperclip size={12} />
              <span className="text-xs">{file.name}</span>
              <Button
                className="h-5 w-5 p-0 text-slate-500 hover:text-slate-900"
                onClick={() => onAttachmentsChange(attachments.filter((entry) => entry.id !== file.id))}
                size="icon"
                type="button"
                variant="ghost"
              >
                <X size={12} />
              </Button>
            </Badge>
          ))}
        </div>
      ) : null}

      <div
        className={cn(
          'rounded-2xl border border-dashed p-4 transition',
          isDragging
            ? 'border-slate-900 bg-slate-100/90 shadow-sm'
            : 'border-slate-200 bg-white/70',
        )}
        onDragEnd={() => setIsDragging(false)}
        onDragLeave={() => setIsDragging(false)}
        onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = 'copy'
          setIsDragging(true)
        }}
        onDrop={(event) => {
          event.preventDefault()
          setIsDragging(false)
          handleFiles(event.dataTransfer.files)
        }}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-slate-700 shadow-sm">
              <Upload size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">Attach files</p>
              <p className="text-xs text-slate-500">
                Drag and drop or browse to add PDFs, docs, or images.
              </p>
            </div>
          </div>
          <Button
            onClick={() => fileRef.current?.click()}
            type="button"
            variant="secondary"
          >
            Browse files
          </Button>
        </div>
        <Input
          aria-label="Attach files"
          className="sr-only"
          id={fileInputId}
          multiple
          onChange={(event) => {
            handleFiles(event.target.files)
            event.target.value = ''
          }}
          ref={fileRef}
          type="file"
        />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white/80 p-3 shadow-sm">
        <Textarea
          className="min-h-[120px] border-transparent bg-transparent shadow-none focus-visible:ring-0"
          onChange={(event) => onTextChange(event.target.value)}
          placeholder="Type your message, agenda, or notes..."
          value={text}
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            aria-label={useMic ? 'Stop voice input' : 'Start voice input'}
            className={useMic ? 'bg-slate-900 text-white hover:bg-slate-800' : ''}
            disabled={!micSupported}
            onClick={onMicToggle}
            title={useMic ? 'Stop voice input' : 'Start voice input'}
            type="button"
            variant="outline"
          >
            <Mic size={16} />
            {useMic ? 'Listening' : 'Voice'}
          </Button>
          <Button
            className={useWeb ? 'bg-teal-600 text-white hover:bg-teal-500' : ''}
            onClick={onWebToggle}
            type="button"
            variant="outline"
          >
            <Globe size={16} />
            Search
          </Button>
          <ModelSelector model={model} models={models} onChange={onModelChange} />
        </div>

        <Button
          disabled={!canSubmit || status === 'streaming'}
          onClick={onSubmit}
          type="button"
          variant="default"
        >
          <Send size={16} />
          {status === 'streaming' ? 'Streaming' : 'Send'}
        </Button>
      </div>

      {micError ? <p className="text-xs font-medium text-rose-600">{micError}</p> : null}
      {useMic && !micError ? (
        <p className="text-xs text-slate-500">Listening... speak to fill the prompt.</p>
      ) : null}
    </div>
  )
}
