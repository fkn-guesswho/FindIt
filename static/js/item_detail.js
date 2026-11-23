
const slides = document.querySelectorAll('.carousel-slide');

let currentSlide = 0;

const counter = document.getElementById('current-slide');
const total = document.getElementById('total-slides');

if (slides.length > 0) {
    total.textContent = slides.length;

    function showSlide(index) {
        slides[currentSlide].classList.remove('active');

        currentSlide = (index + slides.length) % slides.length;

        slides[currentSlide].classList.add('active');

        counter.textContent = currentSlide + 1;
    }

    function changeSlide(direction) {
        showSlide(currentSlide + direction);
    }
}
