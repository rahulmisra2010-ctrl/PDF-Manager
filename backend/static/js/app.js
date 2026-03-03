// Auto-dismiss flash messages after 4 seconds
document.addEventListener('DOMContentLoaded', function () {
    setTimeout(function () {
        if (typeof bootstrap !== 'undefined') {
            document.querySelectorAll('.alert').forEach(function (alert) {
                var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            });
        } else {
            document.querySelectorAll('.alert').forEach(function (alert) {
                alert.style.display = 'none';
            });
        }
    }, 4000);
});
