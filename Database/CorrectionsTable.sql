-- --------------------------------------------------------
-- Host:                         192.168.0.128
-- Server version:               10.11.11-MariaDB-0+deb12u1 - Debian 12
-- Server OS:                    debian-linux-gnu
-- HeidiSQL Version:             12.11.0.7065
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Dumping database structure for repeater
CREATE DATABASE IF NOT EXISTS `repeater` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `repeater`;

-- Dumping structure for table repeater.corrections
CREATE TABLE IF NOT EXISTS `corrections` (
  `detect` tinytext DEFAULT NULL,
  `correct` tinytext DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Dumping data for table repeater.corrections: ~54 rows (approximately)
INSERT IGNORE INTO `corrections` (`detect`, `correct`) VALUES
	('kodak', 'q'),
	('kordak', 'q'),
	('alpha', 'a'),
	('bravo', 'b'),
	('charlie', 'c'),
	('delta', 'd'),
	('echo', 'e'),
	('foxtrot', 'f'),
	('golf', 'g'),
	('hotel', 'h'),
	('india', 'i'),
	('juliet', 'j'),
	('kilo', 'k'),
	('lima', 'l'),
	('mike', 'm'),
	('november', 'n'),
	('oscar', 'o'),
	('papa', 'p'),
	('quebec', 'q'),
	('romeo', 'r'),
	('sierra', 's'),
	('tango', 't'),
	('uniform', 'u'),
	('victor', 'v'),
	('whiskey', 'w'),
	('x-ray', 'x'),
	('xray', 'x'),
	('yankee', 'y'),
	('zulu', 'z'),
	('king', 'k'),
	('charles', 'c'),
	('one', '1'),
	('two', '2'),
	('three', '3'),
	('four', '4'),
	('five', '5'),
	('six', '6'),
	('seven', '7'),
	('eight', '8'),
	('nine', '9'),
	('zero', '0'),
	('box', 'b'),
	('key local', 'k'),
	('niner', '9'),
	('kilowatt', 'k'),
	('friends', 'f'),
	('cielo', 'k'),
	('celo', 'k'),
	('quadec', 'q'),
	('hilo', 'k'),
	('hordak', 'q'),
	('fox', 'f'),
	('zed', 'z'),
	('hopper', 'p');

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
