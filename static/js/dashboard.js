// dashboard.js

// Initialize Chart.js
const ctx = document.getElementById('mainChart').getContext('2d');

const salesData = {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [{
        label: 'Monthly Sales ($)',
        data: [12000, 19000, 15000, 25000, 22000, 30000],
        borderColor: '#4F46E5', // Indigo-600
        backgroundColor: 'rgba(79, 70, 229, 0.1)',
        borderWidth: 3,
        fill: true,
        tension: 0.4 // Makes the line curvy
    }]
};

const mainChart = new Chart(ctx, {
    type: 'line',
    data: salesData,
    options: {
        responsive: true,
        plugins: {
            legend: {
                display: false
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                grid: {
                    display: false
                }
            },
            x: {
                grid: {
                    display: false
                }
            }
        }
    }
});

// Example: Function to dynamically update a stat
function updateStat(id, newValue) {
    const element = document.getElementById(id);
    if (element) element.innerText = newValue;
}