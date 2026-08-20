(function () {
  var scoreEl = document.getElementById("score");
  var button = document.getElementById("clicker");
  var score = 0;
  var timeLeft = 10;
  var running = true;

  button.addEventListener("click", function () {
    if (!running) return;
    score += 1;
    scoreEl.textContent = String(score);
  });

  var timer = setInterval(function () {
    timeLeft -= 1;
    if (timeLeft <= 0) {
      running = false;
      button.disabled = true;
      button.textContent = "Time's up! Final score: " + score;
      clearInterval(timer);
    }
  }, 1000);
})();
