// Parses an uploaded workout-history JSON file and validates that it's
// a list of {date, exercise, sets:[]} entries.

window.UI = window.UI || {};

window.UI.parseUploadedHistory = async function (file) {
  const text = await file.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    throw new Error(`Not valid JSON: ${e.message}`);
  }

  let history;
  if (Array.isArray(parsed)) {
    history = parsed;
  } else if (parsed && Array.isArray(parsed.workouts)) {
    history = parsed.workouts; // user pasted a {workouts:[...]} object
  } else if (parsed && parsed.users) {
    throw new Error(
      `Multi-user file detected — paste only one user's "workouts" array, or use the sample-history endpoint.`,
    );
  } else {
    throw new Error(`Expected a JSON array of workout entries.`);
  }

  if (history.length === 0) {
    throw new Error(`Workout history is empty.`);
  }

  // Light validation on first entry
  const first = history[0];
  if (!first.date || !first.exercise || !Array.isArray(first.sets)) {
    throw new Error(
      `Entries must have {date, exercise, sets:[]}. Got keys: ${Object.keys(first).join(", ")}`,
    );
  }

  return history;
};
