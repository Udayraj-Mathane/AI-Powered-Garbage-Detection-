// Toggle Sidebar with Arrow Icon
document.getElementById('sidebarArrow').addEventListener('click', function () {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');
    const arrowIcon = document.querySelector('#sidebarArrow i');

    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('shifted');

    // Change arrow direction
    if (sidebar.classList.contains('collapsed')) {
        arrowIcon.classList.remove('fa-arrow-left');
        arrowIcon.classList.add('fa-arrow-right');
    } else {
        arrowIcon.classList.remove('fa-arrow-right');
        arrowIcon.classList.add('fa-arrow-left');
    }
});