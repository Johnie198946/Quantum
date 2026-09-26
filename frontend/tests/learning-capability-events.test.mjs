import assert from 'node:assert/strict';
import test from 'node:test';
import { consumeQCPEvent } from '../src/features/quantum-workspace/qcpEventRegistry.js';

test('learning events retain the real exercise and hint; unsupported versions fall back', () => {
  const event = { type: 'learning.exercise', version: 1, renderer: 'learning_exercise', renderer_version: 1,
    payload: { id: 'exercise-1', status: 'draft', book_title: '统计学', section_title: '加权平均', hint: '先比较样本量。' } };
  const result = consumeQCPEvent(event);
  assert.equal(result.path, 'learning_exercise');
  assert.equal(result.payload.id, 'exercise-1');
  assert.match(result.text, /先比较样本量/);
  assert.equal(consumeQCPEvent({ ...event, renderer_version: 2 }).path, 'answer');
  assert.equal(consumeQCPEvent({ ...event, renderer: 'workflow' }), null);
});
