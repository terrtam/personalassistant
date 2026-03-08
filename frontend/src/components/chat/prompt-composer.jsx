import { Globe, Mic, Paperclip, Send, X } from 'lucide-react'
import { useRef } from 'react'

import { ModelSelector } from './model-selector'

export function PromptComposer({
  attachments,
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
    <div className="composer">
        {attachments.length ? (
          <div className="attachments">
            {attachments.map((file) => (
              <span className="file-pill" key={file.id}>
                {file.name}
                <button
                  className="remove-file"
                  onClick={() => onAttachmentsChange(attachments.filter((entry) => entry.id !== file.id))}
                  type="button"
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <textarea
          className="textarea"
          onChange={(event) => onTextChange(event.target.value)}
          placeholder="Type your message..."
          rows={3}
          value={text}
        />

        <div className="composer-footer">
          <div className="tool-row">
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
            <button className="btn btn-secondary" onClick={() => fileRef.current?.click()} type="button">
              <Paperclip size={16} />
              Attach
            </button>
            <button className={`btn ${useMic ? 'btn-primary' : 'btn-ghost'}`} onClick={onMicToggle} type="button">
              <Mic size={16} />
            </button>
            <button className={`btn ${useWeb ? 'btn-primary' : 'btn-ghost'}`} onClick={onWebToggle} type="button">
              <Globe size={16} />
              Search
            </button>
            <ModelSelector model={model} models={models} onChange={onModelChange} />
          </div>

          <button
            className="btn btn-primary"
            disabled={!canSubmit || status === 'streaming'}
            onClick={onSubmit}
            type="button"
          >
            <Send size={16} />
            {status === 'streaming' ? 'Streaming' : 'Send'}
          </button>
        </div>
    </div>
  )
}
