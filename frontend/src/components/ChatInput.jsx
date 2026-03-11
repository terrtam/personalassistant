import { Mic, MicOff, SendHorizontal } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { CalendarPicker } from './CalendarPicker'
import { Button } from './ui/button'
import { Input } from './ui/input'

function ChatInput({ value, onChange, onSend, isLoading }) {
  const [isListening, setIsListening] = useState(false)
  const [micError, setMicError] = useState('')
  const recognitionRef = useRef(null)
  const baseTextRef = useRef('')
  const capturedRef = useRef('')

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop()
      } catch {
        // no-op
      }
    }
  }, [])

  const handleSubmit = (event) => {
    event.preventDefault()
    onSend(value)
  }

  const mergeTranscript = (base, spoken) => {
    if (base && spoken) return `${base} ${spoken}`.trim()
    return (base || spoken || '').trim()
  }

  const startListening = () => {
    if (typeof window === 'undefined') return
    const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognitionApi) {
      setMicError('Voice input is not supported in this browser.')
      return
    }

    setMicError('')
    baseTextRef.current = value.trim()
    capturedRef.current = ''

    if (!recognitionRef.current) {
      const recognition = new SpeechRecognitionApi()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => {
        setIsListening(true)
      }

      recognition.onresult = (event) => {
        let finalChunk = ''
        let interimChunk = ''

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const entry = event.results[i]
          const spoken = entry[0]?.transcript?.trim() ?? ''
          if (!spoken) continue
          if (entry.isFinal) finalChunk += ` ${spoken}`
          else interimChunk += ` ${spoken}`
        }

        if (finalChunk.trim()) {
          capturedRef.current = mergeTranscript(capturedRef.current, finalChunk.trim())
        }

        const liveTranscript = mergeTranscript(capturedRef.current, interimChunk.trim())
        onChange(mergeTranscript(baseTextRef.current, liveTranscript))
      }

      recognition.onerror = (event) => {
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          setMicError('Microphone permission is blocked. Allow access and try again.')
        } else {
          setMicError(`Voice input failed: ${event.error}`)
        }
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
      }

      recognitionRef.current = recognition
    }

    try {
      recognitionRef.current.start()
    } catch {
      setMicError('Voice input could not be started. Try again.')
      setIsListening(false)
    }
  }

  const stopListening = () => {
    try {
      recognitionRef.current?.stop()
    } catch {
      // no-op
    }
    setIsListening(false)
  }

  const toggleListening = () => {
    if (isListening) stopListening()
    else startListening()
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="h-11 min-w-[200px] flex-1"
          placeholder="Ask about your schedule, meetings, or notes..."
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <CalendarPicker onSelectText={(text) => onChange(text)} />
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="h-11 w-11"
          aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
          onClick={toggleListening}
        >
          {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </Button>
        <Button type="submit" className="h-11 px-4" disabled={isLoading || !value.trim()}>
          <SendHorizontal className="h-4 w-4" />
          Send
        </Button>
      </div>
      <p className={micError ? 'text-xs text-rose-600' : 'text-xs text-slate-500'}>
        {micError ? micError : 'Tip: Pick a date to prefill a scheduling request.'}
      </p>
    </form>
  )
}

export { ChatInput }
