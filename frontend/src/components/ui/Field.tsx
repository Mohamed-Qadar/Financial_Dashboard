"use client";

import { type InputHTMLAttributes, type ReactNode, useId, useState } from "react";

import { Icon } from "./Icon";

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  /** One or more messages; the input is marked invalid and linked to them. */
  error?: string | string[];
}

function messagesOf(error: FieldProps["error"]): string[] {
  if (error === undefined) return [];
  return (Array.isArray(error) ? error : [error]).filter((message) => message !== "");
}

function Shell({
  id,
  label,
  hint,
  errors,
  required,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  errors: string[];
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="ui-field" data-invalid={errors.length > 0 || undefined}>
      <label htmlFor={id} className="ui-field-label">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="ui-field-hint">
          {hint}
        </p>
      ) : null}
      {errors.length > 0 ? (
        <ul id={`${id}-error`} className="ui-field-error" role="list">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function describedBy(id: string, hint: string | undefined, errors: string[]) {
  const ids = [hint ? `${id}-hint` : null, errors.length > 0 ? `${id}-error` : null].filter(
    Boolean,
  );
  return ids.length > 0 ? ids.join(" ") : undefined;
}

/** Labelled text input with hint and error messages wired up for assistive technology. */
export function TextField({ label, hint, error, required, ...input }: FieldProps) {
  const id = useId();
  const errors = messagesOf(error);
  return (
    <Shell id={id} label={label} hint={hint} errors={errors} required={required}>
      <input
        {...input}
        id={id}
        className="ui-input"
        required={required}
        aria-invalid={errors.length > 0 || undefined}
        aria-describedby={describedBy(id, hint, errors)}
      />
    </Shell>
  );
}

/** Password input with a show/hide toggle (a real button, so it works with the keyboard). */
export function PasswordField({
  label,
  hint,
  error,
  required,
  showLabel,
  hideLabel,
  ...input
}: FieldProps & { showLabel: string; hideLabel: string }) {
  const id = useId();
  const errors = messagesOf(error);
  const [visible, setVisible] = useState(false);
  return (
    <Shell id={id} label={label} hint={hint} errors={errors} required={required}>
      <div className="ui-input-group">
        <input
          {...input}
          id={id}
          type={visible ? "text" : "password"}
          className="ui-input"
          required={required}
          autoCapitalize="off"
          spellCheck={false}
          aria-invalid={errors.length > 0 || undefined}
          aria-describedby={describedBy(id, hint, errors)}
        />
        <button
          type="button"
          className="ui-input-addon"
          aria-controls={id}
          aria-pressed={visible}
          aria-label={visible ? hideLabel : showLabel}
          onClick={() => setVisible((value) => !value)}
        >
          <Icon name={visible ? "eyeOff" : "eye"} size={18} />
        </button>
      </div>
    </Shell>
  );
}
