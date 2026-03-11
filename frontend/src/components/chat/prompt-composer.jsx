import { Globe, Mic, Paperclip, Send, X } from 'lucide-react'
import { useRef } from 'react'

import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
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
  const fileRef = useRef(null)
  const canSubmit = text.trim().length > 0 || attachments.length > 0

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
          <input
            hidden
            multiple
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []).map((file) => ({
                id: `${file.name}-${file.lastModified}`,
                name: file.name,
              }))
              onAttachmentsChange(files)
            }}
            ref={fileRef}
            type="file"
          />
          <Button onClick={() => fileRef.current?.click()} type="button" variant="secondary">
            <Paperclip size={16} />
            Attach
          </Button>
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
