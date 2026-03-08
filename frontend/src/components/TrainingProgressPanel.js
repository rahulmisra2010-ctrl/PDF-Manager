/**
 * TrainingProgressPanel.js — Training status & statistics panel.
 *
 * Props:
 *   status          {string}   'idle' | 'in_progress' | 'completed' | 'failed'
 *   samplesCount    {number}
 *   trainedSamples  {number}
 *   totalRules      {number}
 *   trainedFields   {number}
 *   lastSession     {object|null}
 *   onTrain         {func}     Trigger training
 *   loadingTrain    {boolean}
 *   error           {string}
 */

import React from 'react';

function TrainingProgressPanel({
  status = 'idle',
  samplesCount = 0,
  trainedSamples = 0,
  totalRules = 0,
  trainedFields = 0,
  lastSession = null,
  onTrain,
  loadingTrain = false,
  error = '',
}) {
  const progressPct =
    samplesCount > 0 ? Math.round((trainedSamples / samplesCount) * 100) : 0;

  const statusLabel = {
    idle: 'Idle — awaiting data',
    in_progress: 'Training in progress…',
    completed: 'Training complete',
    failed: 'Training failed',
  }[status] || status;

  return (
    <div className="training-panel">
      <h3 className="training-panel__title">
        🧠 Training Pipeline
      </h3>

      {/* Stats */}
      <div className="training-panel__stats">
        <div className="training-stat">
          <span className="training-stat__value">{samplesCount}</span>
          <span className="training-stat__label">Total<br/>Samples</span>
        </div>
        <div className="training-stat">
          <span className="training-stat__value">{trainedSamples}</span>
          <span className="training-stat__label">Trained<br/>Samples</span>
        </div>
        <div className="training-stat">
          <span className="training-stat__value">{totalRules}</span>
          <span className="training-stat__label">Logic<br/>Rules</span>
        </div>
        <div className="training-stat">
          <span className="training-stat__value">{trainedFields}</span>
          <span className="training-stat__label">Confirmed<br/>Fields</span>
        </div>
      </div>

      {/* Progress bar */}
      {samplesCount > 0 && (
        <div>
          <div className="training-panel__progress">
            <div
              className="training-panel__progress-bar"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="training-panel__message">
            {trainedSamples} of {samplesCount} samples confirmed ({progressPct}%)
          </p>
        </div>
      )}

      {/* Status row */}
      <div className="training-panel__row">
        <div className="training-panel__status">
          <span
            className={`status-dot status-dot--${
              loadingTrain ? 'training' : status
            }`}
          />
          {loadingTrain ? 'Training in progress…' : statusLabel}
        </div>

        <button
          className="adv-btn adv-btn--train"
          onClick={onTrain}
          disabled={loadingTrain || (samplesCount === 0 && totalRules === 0)}
          title={
            samplesCount === 0 && totalRules === 0
              ? 'Upload at least one sample PDF or logic file first'
              : 'Run training pipeline'
          }
        >
          {loadingTrain ? '⏳ Training…' : '🚀 Train Model'}
        </button>
      </div>

      {/* Last session info */}
      {lastSession && (
        <p className="training-panel__message">
          Last trained:{' '}
          {lastSession.completed_at
            ? new Date(lastSession.completed_at).toLocaleString()
            : 'In progress'}
          {lastSession.trained_fields_count > 0 &&
            ` · ${lastSession.trained_fields_count} fields`}
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="training-panel__error">⚠️ {error}</p>
      )}
    </div>
  );
}

export default TrainingProgressPanel;
