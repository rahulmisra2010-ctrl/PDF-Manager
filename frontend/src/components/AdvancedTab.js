/**
 * AdvancedTab.js — Master component for the Advanced training & suggestion tab.
 *
 * Two-column layout:
 *   Left  — SamplePDFSection  (upload & manage sample PDFs)
 *   Right — LogicRuleSection  (upload & manage logic/rules documents)
 *
 * Below:
 *   TrainingProgressPanel  (training status, stats, trigger)
 *   SuggestionEngineConfig (configure suggestion weights & thresholds)
 */

import React, { useCallback, useEffect, useState } from 'react';
import SamplePDFSection from './SamplePDFSection';
import LogicRuleSection from './LogicRuleSection';
import TrainingProgressPanel from './TrainingProgressPanel';
import SuggestionEngineConfig from './SuggestionEngineConfig';
import {
  uploadTrainingSample,
  listTrainingSamples,
  markTrainingFields,
  deleteTrainingSample,
  uploadLogicRules,
  listLogicRules,
  deleteLogicRule,
  triggerTraining,
  getTrainingStatus,
} from '../services/api';
import '../styles/advanced.css';

function AdvancedTab() {
  // Sample PDFs state
  const [samples, setSamples] = useState([]);
  const [loadingSample, setLoadingSample] = useState(false);
  const [sampleError, setSampleError] = useState('');

  // Logic rules state
  const [logicFiles, setLogicFiles] = useState([]);
  const [loadingLogic, setLoadingLogic] = useState(false);
  const [logicError, setLogicError] = useState('');

  // Training state
  const [trainingStatus, setTrainingStatus] = useState({
    status: 'idle',
    total_samples: 0,
    trained_samples: 0,
    total_rules: 0,
    trained_fields_total: 0,
    last_session: null,
  });
  const [loadingTrain, setLoadingTrain] = useState(false);
  const [trainError, setTrainError] = useState('');

  // Suggestion engine config (local — not persisted to backend yet)
  const [suggConfig, setSuggConfig] = useState({
    similarityThreshold: 70,
    confidenceThreshold: 85,
    maxSuggestions: 3,
    weightSamplePDF: 40,
    weightLogicRule: 40,
    weightHistory: 20,
  });

  // ── Load data on mount ──────────────────────────────────────────

  const loadSamples = useCallback(async () => {
    try {
      const data = await listTrainingSamples();
      setSamples(data.samples || []);
    } catch (err) {
      setSampleError(err.message);
    }
  }, []);

  const loadLogicFiles = useCallback(async () => {
    try {
      const data = await listLogicRules();
      setLogicFiles(data.files || []);
    } catch (err) {
      setLogicError(err.message);
    }
  }, []);

  const loadTrainingStatus = useCallback(async () => {
    try {
      const data = await getTrainingStatus();
      setTrainingStatus(data);
    } catch (err) {
      // Non-critical — don't show error for status polling
    }
  }, []);

  useEffect(() => {
    loadSamples();
    loadLogicFiles();
    loadTrainingStatus();
  }, [loadSamples, loadLogicFiles, loadTrainingStatus]);

  // ── Sample PDF handlers ─────────────────────────────────────────

  const handleUploadSample = useCallback(async (file) => {
    setLoadingSample(true);
    setSampleError('');
    try {
      await uploadTrainingSample(file);
      await loadSamples();
      await loadTrainingStatus();
    } catch (err) {
      setSampleError(err.message);
    } finally {
      setLoadingSample(false);
    }
  }, [loadSamples, loadTrainingStatus]);

  const handleMarkFields = useCallback(async (trainingId, markedFields) => {
    try {
      const updated = await markTrainingFields(trainingId, markedFields);
      setSamples((prev) =>
        prev.map((s) => (s.training_id === trainingId ? updated : s)),
      );
      await loadTrainingStatus();
    } catch (err) {
      setSampleError(err.message);
    }
  }, [loadTrainingStatus]);

  const handleDeleteSample = useCallback(async (trainingId) => {
    try {
      await deleteTrainingSample(trainingId);
      setSamples((prev) => prev.filter((s) => s.training_id !== trainingId));
      await loadTrainingStatus();
    } catch (err) {
      setSampleError(err.message);
    }
  }, [loadTrainingStatus]);

  // ── Logic rule handlers ─────────────────────────────────────────

  const handleUploadLogic = useCallback(async (file) => {
    setLoadingLogic(true);
    setLogicError('');
    try {
      await uploadLogicRules(file);
      await loadLogicFiles();
      await loadTrainingStatus();
    } catch (err) {
      setLogicError(err.message);
    } finally {
      setLoadingLogic(false);
    }
  }, [loadLogicFiles, loadTrainingStatus]);

  const handleDeleteLogic = useCallback(async (ruleId) => {
    try {
      await deleteLogicRule(ruleId);
      setLogicFiles((prev) => prev.filter((f) => f.rule_id !== ruleId));
      await loadTrainingStatus();
    } catch (err) {
      setLogicError(err.message);
    }
  }, [loadTrainingStatus]);

  // ── Training handler ────────────────────────────────────────────

  const handleTrain = useCallback(async () => {
    setLoadingTrain(true);
    setTrainError('');
    try {
      await triggerTraining(false);
      await loadTrainingStatus();
    } catch (err) {
      setTrainError(err.message);
    } finally {
      setLoadingTrain(false);
    }
  }, [loadTrainingStatus]);

  return (
    <div className="advanced-tab">
      {/* Header */}
      <div className="advanced-tab__header">
        <div>
          <h2 className="advanced-tab__title">🔥 Advanced — Training & Suggestions</h2>
          <p className="advanced-tab__subtitle">
            Upload sample PDFs and logic documents to train the suggestion engine
          </p>
        </div>
      </div>

      {/* Two-column split */}
      <div className="advanced-tab__split">
        <SamplePDFSection
          samples={samples}
          onUpload={handleUploadSample}
          onMarkFields={handleMarkFields}
          onDelete={handleDeleteSample}
          loading={loadingSample}
          error={sampleError}
        />
        <LogicRuleSection
          logicFiles={logicFiles}
          onUpload={handleUploadLogic}
          onDelete={handleDeleteLogic}
          loading={loadingLogic}
          error={logicError}
        />
      </div>

      {/* Training progress panel */}
      <TrainingProgressPanel
        status={trainingStatus.status}
        samplesCount={trainingStatus.total_samples}
        trainedSamples={trainingStatus.trained_samples}
        totalRules={trainingStatus.total_rules}
        trainedFields={trainingStatus.trained_fields_total}
        lastSession={trainingStatus.last_session}
        onTrain={handleTrain}
        loadingTrain={loadingTrain}
        error={trainError}
      />

      {/* Suggestion engine configuration */}
      <SuggestionEngineConfig
        config={suggConfig}
        onChange={setSuggConfig}
      />
    </div>
  );
}

export default AdvancedTab;
